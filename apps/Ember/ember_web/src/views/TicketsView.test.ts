import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/http";
import { ticketsClient, type Ticket } from "../api/TicketsClient";
import TicketsView from "./TicketsView.vue";

vi.mock("../api/TicketsClient", () => ({
  ticketsClient: { list: vi.fn(), get: vi.fn(), create: vi.fn(), comment: vi.fn(), close: vi.fn() },
}));

const client = vi.mocked(ticketsClient);

// jsdom has no <dialog> methods.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

const ticket = (id: number, extra: Partial<Ticket> = {}): Ticket => ({
  id,
  type: "bug",
  title: `Ticket ${id}`,
  description: `Description ${id}`,
  status: "open",
  created_at: "2026-10-10T10:00:00+00:00",
  updated_at: "2026-10-10T11:00:00+00:00",
  closed_at: null,
  ...extra,
});

const mounted: ReturnType<typeof mount>[] = [];

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  document.body.innerHTML = '';
});

async function mountView() {
  const wrapper = mount(TicketsView, { attachTo: document.body });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}

const rows = (wrapper: ReturnType<typeof mount>) => wrapper.findAll("button.ticket-row");
const button = (wrapper: ReturnType<typeof mount>, text: string) =>
  wrapper.findAll("button").find((b) => b.text() === text)!;

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue([ticket(2, { status: "in_progress" }), ticket(1)]);
});

describe("TicketsView", () => {
  it("lists the account's tickets with a status word", async () => {
    const wrapper = await mountView();

    expect(rows(wrapper)).toHaveLength(2);
    expect(rows(wrapper)[0]!.text()).toContain("Ticket 2");
    expect(rows(wrapper)[0]!.text()).toContain("In progress");
    expect(rows(wrapper)[1]!.text()).toContain("Open");
    expect(client.list).toHaveBeenCalledWith(undefined);
  });

  it("filters by status", async () => {
    const wrapper = await mountView();

    await wrapper.findAll("button.segment").find((b) => b.text() === "Closed")!.trigger("click");
    await flushPromises();

    expect(client.list).toHaveBeenLastCalledWith("closed");
  });

  it("explains an empty list", async () => {
    client.list.mockResolvedValue([]);
    const wrapper = await mountView();

    expect(wrapper.text()).toContain("You have no tickets yet.");
  });

  it("shows a load error", async () => {
    client.list.mockRejectedValue(new ApiError(502, "mcp_server is unreachable"));
    const wrapper = await mountView();

    expect(wrapper.find(".error").text()).toContain("mcp_server is unreachable");
  });

  it("files a ticket, tells the user its number and reloads", async () => {
    client.create.mockResolvedValue({ ticket: ticket(9), duplicate: false, group_size: 1 });
    const wrapper = await mountView();
    await button(wrapper, "New ticket").trigger("click");

    const submit = wrapper.find("button.submit-ticket");
    expect(submit.attributes("disabled")).toBeDefined();
    await wrapper.find("input[aria-label='Title']").setValue("Email fails");
    await wrapper.find("textarea[aria-label='Description']").setValue("It does not send");
    expect(submit.attributes("disabled")).toBeUndefined();
    await submit.trigger("click");
    await flushPromises();

    expect(client.create).toHaveBeenCalledWith({ type: "bug", title: "Email fails", description: "It does not send" });
    expect(wrapper.find(".notice").text()).toBe("Ticket 9 filed. Support will review it.");
    expect(client.list).toHaveBeenCalledTimes(2);
  });

  it("keeps the draft and shows the error when filing fails", async () => {
    client.create.mockRejectedValue(new ApiError(400, "The title is not acceptable."));
    const wrapper = await mountView();
    await button(wrapper, "New ticket").trigger("click");
    await wrapper.find("input[aria-label='Title']").setValue("x");
    await wrapper.find("textarea[aria-label='Description']").setValue("y");

    await wrapper.find("button.submit-ticket").trigger("click");
    await flushPromises();

    expect(wrapper.find(".form-error").text()).toBe("The title is not acceptable.");
    expect((wrapper.find("input[aria-label='Title']").element as HTMLInputElement).value).toBe("x");
  });

  it("opens a ticket with its thread and sends a reply", async () => {
    client.get.mockResolvedValue(
      ticket(1, {
        comments: [
          { id: 1, ticket_id: 1, author: "root", author_role: "staff", body: "Please send the log.", created_at: "2026-10-10T12:00:00+00:00" },
          { id: 2, ticket_id: 1, author: "ada", author_role: "ai", body: "Log attached.", created_at: "2026-10-10T12:05:00+00:00" },
        ],
      }),
    );
    client.comment.mockResolvedValue(ticket(1, { comments: [] }));
    const wrapper = await mountView();

    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();

    expect(client.get).toHaveBeenCalledWith(1);
    const thread = wrapper.find(".thread").text();
    expect(thread).toContain("Support");
    expect(thread).toContain("Please send the log.");
    expect(thread).toContain("Assistant, for you");

    await wrapper.find("textarea[aria-label='Reply']").setValue("More details");
    await button(wrapper, "Send").trigger("click");
    await flushPromises();

    expect(client.comment).toHaveBeenCalledWith(1, "More details");
  });

  it("closes a ticket only after confirming", async () => {
    client.get.mockResolvedValue(ticket(1, { comments: [] }));
    client.close.mockResolvedValue(ticket(1, { status: "closed" }));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();

    await button(wrapper, "Close ticket").trigger("click");
    expect(client.close).not.toHaveBeenCalled();
    await button(wrapper, "Close the ticket").trigger("click");
    await flushPromises();

    expect(client.close).toHaveBeenCalledWith(1);
  });

  it("offers no close button on a closed ticket", async () => {
    client.get.mockResolvedValue(ticket(1, { status: "closed", comments: [] }));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();

    expect(wrapper.findAll("button").some((b) => b.text() === "Close ticket")).toBe(false);
  });

  it("keeps the newest status result when an older request finishes later", async () => {
    let finishOld!: (tickets: Ticket[]) => void;
    client.list.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
    const wrapper = await mountView();
    client.list.mockResolvedValue([ticket(3, { status: "closed" })]);
    await wrapper.findAll("button.segment").find((b) => b.text() === "Closed")!.trigger("click");
    await flushPromises();
    finishOld([ticket(1)]);
    await flushPromises();
    expect(rows(wrapper)).toHaveLength(1);
    expect(rows(wrapper)[0]!.text()).toContain("Ticket 3");
    expect(rows(wrapper)[0]!.text()).toContain("Closed");
  });

  it("does not reopen a dismissed detail when its request finishes", async () => {
    let finishDetail!: (ticket: Ticket) => void;
    client.get.mockImplementationOnce(() => new Promise((resolve) => { finishDetail = resolve; }));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await wrapper.find('dialog[aria-label="Ticket #1"] button.close').trigger("click");
    finishDetail(ticket(1, { comments: [] }));
    await flushPromises();
    expect(wrapper.find(".detail-title").exists()).toBe(false);
  });

  it("keeps the selected detail when an older detail request finishes", async () => {
    let finishOld!: (ticket: Ticket) => void;
    client.get.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
    client.get.mockResolvedValue(ticket(1, { comments: [] }));
    const wrapper = await mountView();
    await rows(wrapper)[0]!.trigger("click");
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();
    finishOld(ticket(2, { comments: [] }));
    await flushPromises();
    expect(wrapper.find(".detail-title").text()).toBe("Ticket 1");
  });

  it("keeps the reply draft when sending fails", async () => {
    client.get.mockResolvedValue(ticket(1, { comments: [] }));
    client.comment.mockRejectedValue(new ApiError(502, "Support is unreachable."));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();
    await wrapper.find("textarea[aria-label='Reply']").setValue("Keep these details");
    await button(wrapper, "Send").trigger("click");
    await flushPromises();
    expect((wrapper.find("textarea[aria-label='Reply']").element as HTMLTextAreaElement).value).toBe("Keep these details");
    expect(wrapper.find('dialog[aria-label="Ticket #1"] .error').text()).toContain("Support is unreachable.");
  });

  it.each(["comment", "close"] as const)("does not reopen a dismissed detail after %s succeeds", async (operation) => {
    let finishAction!: (ticket: Ticket) => void;
    client.get.mockResolvedValue(ticket(1, { comments: [] }));
    client[operation].mockImplementationOnce(() => new Promise((resolve) => { finishAction = resolve; }));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();
    if (operation === "comment") {
      await wrapper.find("textarea[aria-label='Reply']").setValue("More details");
      await button(wrapper, "Send").trigger("click");
    } else {
      await button(wrapper, "Close ticket").trigger("click");
      await button(wrapper, "Close the ticket").trigger("click");
    }
    await wrapper.find('dialog[aria-label="Ticket #1"] button.close').trigger("click");
    finishAction(ticket(1, { status: operation === "close" ? "closed" : "open", comments: [] }));
    await flushPromises();
    expect(wrapper.find(".detail-title").exists()).toBe(false);
  });
});
