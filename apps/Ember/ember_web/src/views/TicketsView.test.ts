import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/http";
import { ticketsClient, type Ticket } from "../api/TicketsClient";
import TicketsView from "./TicketsView.vue";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../api/TicketsClient", () => ({
  ticketsClient: { list: vi.fn(), get: vi.fn(), create: vi.fn(), comment: vi.fn(), close: vi.fn(), reopen: vi.fn() },
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
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

let router: ReturnType<typeof createRouter>;
async function mountView(path = "/tickets") {
  router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/tickets/:id?", component: TicketsView }] });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(TicketsView, { attachTo: document.body, global: { plugins: [router] } });
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
  it("uses an inline thread and keeps a reply when the selected row is clicked again", async () => {
    client.get.mockResolvedValue(ticket(1, { comments: [] }));
    const wrapper = await mountView("/tickets/1");
    expect(wrapper.find('section.ticket-thread[aria-label="Ticket #1"]').exists()).toBe(true);
    await wrapper.get("textarea[aria-label='Reply']").setValue("Keep this draft");
    await rows(wrapper).find(row => row.text().includes("Ticket 1"))!.trigger("click");
    await flushPromises();
    expect(client.get).toHaveBeenCalledTimes(1);
    expect(wrapper.get<HTMLTextAreaElement>("textarea[aria-label='Reply']").element.value).toBe("Keep this draft");
  });
  it("keeps the conversation and reply draft while filtering or polling the list", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    client.get.mockResolvedValue(ticket(1, { comments: [] }));
    const wrapper = await mountView("/tickets/1");
    await wrapper.get("textarea[aria-label='Reply']").setValue("More context");
    await wrapper.get("input[aria-label='Search ticket titles']").setValue("no match");
    await vi.advanceTimersByTimeAsync(30_000); await flushPromises();
    expect(rows(wrapper)).toHaveLength(0);
    expect(wrapper.get(".detail-title").text()).toBe("Ticket 1");
    expect(wrapper.get<HTMLTextAreaElement>("textarea[aria-label='Reply']").element.value).toBe("More context");
  });
  it("loads an unread update on the selected ticket without clearing a reply", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.spyOn(document, "hidden", "get").mockReturnValue(false);
    client.get.mockResolvedValue(ticket(1, { has_unread: false, comments: [] }));
    const wrapper = await mountView("/tickets/1");
    await wrapper.get("textarea[aria-label='Reply']").setValue("A reply in progress");
    client.list.mockResolvedValue([ticket(1, { has_unread: true })]);
    await vi.advanceTimersByTimeAsync(30_000); await flushPromises();
    client.get.mockResolvedValue(ticket(1, { has_unread: false, comments: [{ id: 9, ticket_id: 1, author: "support", author_role: "staff", body: "New support reply", created_at: "2026-10-21T00:00:00Z" }] }));
    await rows(wrapper)[0]!.trigger("click"); await flushPromises();
    expect(wrapper.get(".thread").text()).toContain("New support reply");
    expect(wrapper.get<HTMLTextAreaElement>("textarea[aria-label='Reply']").element.value).toBe("A reply in progress");
    expect(rows(wrapper)[0]!.classes()).not.toContain("unread");
  });

  it("keeps a ticket seen when its initial list response arrives after the detail", async () => {
    let finishList!: (rows: Ticket[]) => void;
    client.list.mockImplementationOnce(() => new Promise(resolve => { finishList = resolve; }));
    client.get.mockResolvedValue(ticket(1, { has_unread: false }));
    const wrapper = await mountView("/tickets/1");
    finishList([ticket(1, { has_unread: true })]);
    await flushPromises();
    expect(rows(wrapper)[0]!.classes()).not.toContain("unread");
  });
  it("opens a deep link directly and returns to the list when dismissed", async () => {
    client.get.mockResolvedValue(ticket(42));
    const wrapper = await mountView("/tickets/42");
    expect(client.get).toHaveBeenCalledWith(42);
    expect(wrapper.find(".detail-title").text()).toBe("Ticket 42");
    await wrapper.find('section[aria-label="Ticket #42"] button.close').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/tickets");
    expect(wrapper.find(".detail-title").exists()).toBe(false);
  });

  it("updates the address when a row opens", async () => {
    client.get.mockResolvedValue(ticket(1));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/tickets/1");
  });

  it("shows the error for an unknown or foreign deep link", async () => {
    client.get.mockRejectedValue(new ApiError(404, "No ticket 404."));
    const wrapper = await mountView("/tickets/404");
    expect(wrapper.find('section[aria-label="Ticket #404"] .error').text()).toContain("No ticket 404.");
    expect(wrapper.find(".detail-title").exists()).toBe(false);
  });

  it("follows back and forward navigation without keeping the wrong ticket", async () => {
    client.get.mockImplementation(async id => ticket(id));
    const wrapper = await mountView("/tickets/1");
    await router.push("/tickets/2");
    await flushPromises();
    expect(wrapper.find(".detail-title").text()).toBe("Ticket 2");
    router.back();
    await new Promise(resolve => setTimeout(resolve, 0));
    await flushPromises();
    expect(wrapper.find(".detail-title").text()).toBe("Ticket 1");
    router.forward();
    await new Promise(resolve => setTimeout(resolve, 0));
    await flushPromises();
    expect(wrapper.find(".detail-title").text()).toBe("Ticket 2");
  });

  it.each(["oops", "0", "9007199254740992"])("handles invalid deep link %s", async id => {
    const wrapper = await mountView(`/tickets/${id}`);
    expect(wrapper.find(".error").text()).toContain("Invalid ticket id.");
    expect(client.get).not.toHaveBeenCalled();
  });
  it.each(["resolved", "closed"] as const)("reopens a %s ticket without confirmation", async status => {
    client.get.mockResolvedValue(ticket(1, { status }));
    client.reopen.mockResolvedValue(ticket(1));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();
    await button(wrapper, "Reopen ticket").trigger("click");
    await flushPromises();
    expect(client.reopen).toHaveBeenCalledWith(1);
    expect(button(wrapper, "Close ticket").exists()).toBe(true);
  });
  it("explains when the report is grouped with similar reports", async () => {
    client.create.mockResolvedValue({ ticket: ticket(9), duplicate: false, group_size: 4 });
    const wrapper = await mountView();
    await button(wrapper, "New ticket").trigger("click");
    await wrapper.find("input[aria-label='Title']").setValue("Email fails");
    await wrapper.find("textarea[aria-label='Description']").setValue("Details");
    await wrapper.find("button.submit-ticket").trigger("click");
    await flushPromises();
    expect(wrapper.find(".notice").text()).toBe("Ticket #9 filed. 3 other people reported something similar, so yours is grouped with them.");
  });
  it("signals unread support activity and clears it after opening", async () => {
    client.list.mockResolvedValue([ticket(1, { has_unread: true })]);
    client.get.mockResolvedValue(ticket(1, { has_unread: false }));
    const wrapper = await mountView();
    expect(rows(wrapper)[0]!.classes()).toContain("unread");
    expect(rows(wrapper)[0]!.text()).toContain("Support replied");
    await rows(wrapper)[0]!.trigger("click");
    await flushPromises();
    expect(rows(wrapper)[0]!.classes()).not.toContain("unread");
  });
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

    await wrapper.findAll("button.segment").find((b) => b.attributes("data-value") === "closed")!.trigger("click");
    await flushPromises();

    expect(client.list).toHaveBeenCalledTimes(1);
    expect(rows(wrapper)).toHaveLength(0);
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

  it("counts and searches all statuses from one list and sorts by update time", async () => {
    client.list.mockResolvedValue([
      ticket(1, { title: "Email fails", updated_at: "2026-10-10T10:00:00Z" }),
      ticket(2, { title: "Login fails", status: "closed", updated_at: "2026-10-12T10:00:00Z" }),
    ]);
    const wrapper = await mountView();
    expect(wrapper.find('[data-value="all"]').text()).toBe("All (2)");
    expect(wrapper.find('[data-value="closed"]').text()).toBe("Closed (1)");
    expect(rows(wrapper)[0]!.text()).toContain("Login fails");
    await wrapper.find('select[aria-label="Sort tickets"]').setValue("oldest");
    expect(rows(wrapper)[0]!.text()).toContain("Email fails");
    await wrapper.find('input[aria-label="Search ticket titles"]').setValue("EMAIL");
    expect(rows(wrapper)).toHaveLength(1);
    expect(rows(wrapper)[0]!.text()).toContain("Email fails");
    expect(client.list).toHaveBeenCalledTimes(1);
  });

  it("shows character counts and a dated status timeline without inventing a progress date", async () => {
    client.get.mockResolvedValue(ticket(1, { status: "resolved", closed_at: "2026-10-12T10:00:00Z" }));
    const wrapper = await mountView("/tickets/1");
    expect(wrapper.findAll('.timeline time')).toHaveLength(2);
    expect(wrapper.find('.timeline [aria-current="step"]').text()).toContain("Resolved");
    await button(wrapper, "New ticket").trigger("click");
    await wrapper.find("input[aria-label='Title']").setValue("Title");
    await wrapper.find("textarea[aria-label='Description']").setValue("Details");
    expect(wrapper.find("#ticket-title-count").text()).toBe("5/120");
    expect(wrapper.find("#ticket-description-count").text()).toBe("7/4000");
  });

  it("polls every 30 seconds only while visible and cleans up after leaving", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    let hidden = false;
    vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
    const wrapper = await mountView();
    expect(client.list).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(30_000);
    await flushPromises();
    expect(client.list).toHaveBeenCalledTimes(2);
    hidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(60_000);
    expect(client.list).toHaveBeenCalledTimes(2);
    hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(client.list).toHaveBeenCalledTimes(3);
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(client.list).toHaveBeenCalledTimes(3);
  });

  it("does not reopen a dismissed detail when its request finishes", async () => {
    let finishDetail!: (ticket: Ticket) => void;
    client.get.mockImplementationOnce(() => new Promise((resolve) => { finishDetail = resolve; }));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await wrapper.find('section[aria-label="Ticket #1"] button.close').trigger("click");
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
    expect(wrapper.find('section[aria-label="Ticket #1"] .error').text()).toContain("Support is unreachable.");
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
    await wrapper.find('section[aria-label="Ticket #1"] button.close').trigger("click");
    finishAction(ticket(1, { status: operation === "close" ? "closed" : "open", comments: [] }));
    await flushPromises();
    expect(wrapper.find(".detail-title").exists()).toBe(false);
  });
  it("keeps a confirmed close when the initial detail finishes later", async () => {
    let finish!: (value: Ticket) => void;
    client.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    client.close.mockResolvedValue(ticket(1, { status: "closed" }));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await button(wrapper, "Close ticket").trigger("click");
    await button(wrapper, "Close the ticket").trigger("click");
    await flushPromises();
    finish(ticket(1));
    await flushPromises();
    expect(wrapper.findAll("button").some(b => b.text() === "Close ticket")).toBe(false);
  });

  it("locks creation fields while submitting, including after reopening", async () => {
    client.create.mockImplementationOnce(() => new Promise(() => {}));
    const wrapper = await mountView();
    await button(wrapper, "New ticket").trigger("click");
    await wrapper.find("input[aria-label='Title']").setValue("Issue");
    await wrapper.find("textarea[aria-label='Description']").setValue("Details");
    await wrapper.find("button.submit-ticket").trigger("click");
    expect(wrapper.find("input[aria-label='Title']").attributes("disabled")).toBeDefined();
    expect(wrapper.find("textarea[aria-label='Description']").attributes("disabled")).toBeDefined();
    await button(wrapper, "Cancel").trigger("click");
    await button(wrapper, "New ticket").trigger("click");
    expect(wrapper.find("input[aria-label='Title']").attributes("disabled")).toBeDefined();
  });

  it("locks reply editing and competing close while sending", async () => {
    client.get.mockResolvedValue(ticket(1));
    client.comment.mockImplementationOnce(() => new Promise(() => {}));
    const wrapper = await mountView();
    await rows(wrapper)[1]!.trigger("click");
    await flushPromises();
    await wrapper.find("textarea[aria-label='Reply']").setValue("Details");
    await button(wrapper, "Send").trigger("click");
    expect(wrapper.find("textarea[aria-label='Reply']").attributes("disabled")).toBeDefined();
    await button(wrapper, "Close ticket").trigger("click");
    await button(wrapper, "Close the ticket").trigger("click");
    expect(client.close).not.toHaveBeenCalled();
  });
});
