import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import TicketsAdminView from "../../views/TicketsAdminView.vue";
import { ApiError } from "../../api/http";
import { ticketsAdminClient, type AdminTicket, type TicketGroup } from "../../api/TicketsAdminClient";
import TicketsPanel from "./TicketsPanel.vue";

vi.mock("../../api/TicketsAdminClient", () => ({
  ticketsAdminClient: {
    listGroups: vi.fn(), listTickets: vi.fn(), get: vi.fn(), update: vi.fn(), comment: vi.fn(), move: vi.fn(), updateGroup: vi.fn(), stats: vi.fn(),
  },
}));

const client = vi.mocked(ticketsAdminClient);

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

const group = (id: number, extra: Partial<TicketGroup> = {}): TicketGroup => ({
  id,
  title: `Group ${id}`,
  priority: "normal",
  priority_pinned: false,
  ticket_count: 2,
  recent_count: 1,
  open_count: 2,
  last_activity: "2026-10-10T12:00:00+00:00",
  tags: ["email"],
  ...extra,
});

const ticket = (id: number, extra: Partial<AdminTicket> = {}): AdminTicket => ({
  id,
  group_id: 1,
  type: "bug",
  title: `Ticket ${id}`,
  description: `Description ${id}`,
  status: "open",
  priority: "normal",
  effective_priority: "normal",
  assignee: null,
  reporter: "alice",
  source: "user",
  tags: ["email"],
  context: {},
  possible_group_id: null,
  created_at: "2026-10-10T10:00:00+00:00",
  updated_at: "2026-10-10T11:00:00+00:00",
  closed_at: null,
  comments: [],
  ...extra,
});

const FILTERS = { status: "all", priority: "all", tag: "", mode: "groups" } as const;

const mounted: ReturnType<typeof mount>[] = [];

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  document.body.innerHTML = "";
});

async function panel(filters: Record<string, string> = {}) {
  const wrapper = mount(TicketsPanel, { props: { filters: { ...FILTERS, ...filters } as never }, attachTo: document.body });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  client.listGroups.mockResolvedValue([group(1, { priority: "high" }), group(2, { tags: ["ui"], priority_pinned: true })]);
  client.listTickets.mockResolvedValue([ticket(11, { source: "ai_auto" }), ticket(12, { status: "closed", reporter: "bob" })]);
  client.get.mockResolvedValue(ticket(11));
  client.update.mockResolvedValue(ticket(11, { status: "closed" }));
  client.updateGroup.mockResolvedValue(group(1));
  client.comment.mockResolvedValue(ticket(11));
  client.move.mockResolvedValue(ticket(11));
});

describe("TicketsPanel", () => {
  it("lists groups with counts, tags and priority", async () => {
    const wrapper = await panel();

    const rows = wrapper.findAll(".group-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]!.text()).toContain("Group 1");
    expect(rows[0]!.text()).toContain("2 tickets");
    expect(rows[0]!.text()).toContain("1 in 24 h");
    expect((rows[0]!.find("select").element as HTMLSelectElement).value).toBe("high");
    expect(client.listGroups).toHaveBeenCalledWith({});
  });

  it("sends the filters to the server", async () => {
    await panel({ status: "open", priority: "urgent", tag: "email" });

    expect(client.listGroups).toHaveBeenCalledWith({ status: "open", priority: "urgent", tag: "email" });
  });

  it("expands a group to its tickets with source and status", async () => {
    const wrapper = await panel();

    await wrapper.find("button.expand").trigger("click");
    await flushPromises();

    expect(client.listTickets).toHaveBeenCalledWith({ group_id: 1 });
    const text = wrapper.find(".group-tickets").text();
    expect(text).toContain("Ticket 11");
    expect(text).toContain("AI, automatic");
    expect(text).toContain("bob");
    expect(text).toContain("Closed");
  });

  it("opens a ticket in the drawer", async () => {
    const wrapper = await panel();
    await wrapper.find("button.expand").trigger("click");
    await flushPromises();

    await wrapper.find("button.ticket-link").trigger("click");
    await flushPromises();

    expect(client.get).toHaveBeenCalledWith(11);
    expect(wrapper.find("aside.drawer").text()).toContain("Ticket 11");
  });

  it("changes a ticket from the drawer, then reloads groups and shows a notice", async () => {
    const wrapper = await panel();
    await wrapper.find("button.expand").trigger("click");
    await flushPromises();
    await wrapper.find("button.ticket-link").trigger("click");
    await flushPromises();
    client.listGroups.mockClear();

    const select = wrapper.find("select[aria-label='Status']");
    (select.element as HTMLSelectElement).value = "closed";
    await select.trigger("change");
    await flushPromises();

    expect(client.update).toHaveBeenCalledWith(11, { status: "closed" });
    expect(client.listGroups).toHaveBeenCalled();
    expect(wrapper.find("aside.drawer .notice").text()).toBe("Saved.");
  });

  it("shows an error from a failed change and leaves the server value", async () => {
    client.update.mockRejectedValue(new ApiError(400, "The status must be one of: open."));
    const wrapper = await panel();
    await wrapper.find("button.expand").trigger("click");
    await flushPromises();
    await wrapper.find("button.ticket-link").trigger("click");
    await flushPromises();

    const select = wrapper.find("select[aria-label='Status']");
    (select.element as HTMLSelectElement).value = "closed";
    await select.trigger("change");
    await flushPromises();

    expect(wrapper.find("aside.drawer .error").text()).toBe("The status must be one of: open.");
    expect((select.element as HTMLSelectElement).value).toBe("open");
  });

  it("sets a group's priority and shows only the server's value until it answers", async () => {
    const wrapper = await panel();
    const select = wrapper.find(".group-row select");

    (select.element as HTMLSelectElement).value = "urgent";
    await select.trigger("change");

    expect((select.element as HTMLSelectElement).value).toBe("high");
    expect(client.updateGroup).toHaveBeenCalledWith(1, { priority: "urgent" });
  });

  it("unpins a pinned group with the switch and keeps the shown state until the reload", async () => {
    const wrapper = await panel();
    const toggle = wrapper.findAll(".group-row")[1]!.find("input[role='switch']");
    expect((toggle.element as HTMLInputElement).checked).toBe(true);

    (toggle.element as HTMLInputElement).checked = false;
    await toggle.trigger("change");

    expect(client.updateGroup).toHaveBeenCalledWith(2, { pinned: false });
    expect((toggle.element as HTMLInputElement).checked).toBe(true);
  });

  it("lists possible duplicates in review mode", async () => {
    client.listTickets.mockResolvedValue([ticket(21, { possible_group_id: 5, group_id: 9, title: "Mail broken" })]);
    const wrapper = await panel({ mode: "review" });

    expect(client.listTickets).toHaveBeenCalledWith({ possible: true });
    expect(client.listGroups).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Mail broken");
    expect(wrapper.text()).toContain("May belong to group 5");
  });

  it("emits the filters when the user changes them", async () => {
    const wrapper = await panel();

    await wrapper.findAll("button.segment").find((b) => b.text() === "Open")!.trigger("click");

    expect(wrapper.emitted("filter")!.at(-1)).toEqual([{ ...FILTERS, status: "open" }]);
  });

  it("shows a load error and an empty state", async () => {
    client.listGroups.mockRejectedValue(new ApiError(502, "mcp_server is unreachable"));
    let wrapper = await panel();
    expect(wrapper.find(".error").text()).toContain("mcp_server is unreachable");

    client.listGroups.mockResolvedValue([]);
    wrapper = await panel();
    expect(wrapper.text()).toContain("No tickets match.");
  });

  it("keeps the newest group list when an older filter request finishes", async () => {
    let finishOld!: (groups: TicketGroup[]) => void;
    client.listGroups.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
    const wrapper = await panel();
    client.listGroups.mockResolvedValue([group(9, { priority: "urgent" })]);
    await wrapper.setProps({ filters: { ...FILTERS, priority: "urgent" } });
    await flushPromises();
    finishOld([group(1)]);
    await flushPromises();
    expect(wrapper.findAll(".group-row")).toHaveLength(1);
    expect(wrapper.find(".group-row").text()).toContain("Group 9");
  });

  it("keeps the expanded group's tickets when an older expansion finishes", async () => {
    let finishOld!: (tickets: AdminTicket[]) => void;
    const wrapper = await panel();
    client.listTickets.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
    await wrapper.findAll("button.expand")[0]!.trigger("click");
    client.listTickets.mockResolvedValue([ticket(22, { group_id: 2 })]);
    await wrapper.findAll("button.expand")[1]!.trigger("click");
    await flushPromises();
    finishOld([ticket(11)]);
    await flushPromises();
    expect(wrapper.find(".group-tickets").text()).toContain("Ticket 22");
    expect(wrapper.find(".group-tickets").text()).not.toContain("Ticket 11");
  });

  it("does not reopen a dismissed drawer when its detail request finishes", async () => {
    let finishDetail!: (ticket: AdminTicket) => void;
    const wrapper = await panel();
    await wrapper.find("button.expand").trigger("click");
    await flushPromises();
    client.get.mockImplementationOnce(() => new Promise((resolve) => { finishDetail = resolve; }));
    await wrapper.find("button.ticket-link").trigger("click");
    await wrapper.find("aside.drawer button.x").trigger("click");
    finishDetail(ticket(11));
    await flushPromises();
    expect(wrapper.find("aside.drawer").exists()).toBe(false);
  });

  it("keeps the selected drawer when an older detail request finishes", async () => {
    let finishOld!: (ticket: AdminTicket) => void;
    const wrapper = await panel();
    await wrapper.find("button.expand").trigger("click");
    await flushPromises();
    client.get.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
    await wrapper.findAll("button.ticket-link")[0]!.trigger("click");
    client.get.mockResolvedValue(ticket(12));
    await wrapper.findAll("button.ticket-link")[1]!.trigger("click");
    await flushPromises();
    finishOld(ticket(11));
    await flushPromises();
    expect(wrapper.find("aside.drawer .name").text()).toContain("Ticket 12");
  });

  it("does not reopen a dismissed drawer after a change refreshes its detail", async () => {
    let finishRefresh!: (ticket: AdminTicket) => void;
    const wrapper = await panel();
    await wrapper.find("button.expand").trigger("click");
    await flushPromises();
    await wrapper.find("button.ticket-link").trigger("click");
    await flushPromises();
    client.get.mockImplementationOnce(() => new Promise((resolve) => { finishRefresh = resolve; }));
    await wrapper.find("select[aria-label='Status']").setValue("closed");
    await flushPromises();
    await wrapper.find("aside.drawer button.x").trigger("click");
    finishRefresh(ticket(11, { status: "closed" }));
    await flushPromises();
    expect(wrapper.find("aside.drawer").exists()).toBe(false);
  });

  it("loads filters from the URL, preserves other query options, and restores them on navigation", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/tickets", component: TicketsAdminView }] });
    await router.push("/tickets?status=open&priority=urgent&tag=email&source=bookmark");
    const wrapper = mount(TicketsAdminView, { global: { plugins: [router] }, attachTo: document.body });
    mounted.push(wrapper);
    await flushPromises();
    expect(client.listGroups).toHaveBeenLastCalledWith({ status: "open", priority: "urgent", tag: "email" });
    await wrapper.findAll("button.segment").find((b) => b.text() === "Closed")!.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ status: "closed", priority: "urgent", tag: "email", source: "bookmark" });
    await router.push("/tickets?mode=review");
    await flushPromises();
    expect(client.listTickets).toHaveBeenLastCalledWith({ possible: true });
    router.back();
    await flushPromises();
    expect(client.listGroups).toHaveBeenLastCalledWith({ status: "closed", priority: "urgent", tag: "email" });
    expect((wrapper.find("select[aria-label='Priority filter']").element as HTMLSelectElement).value).toBe("urgent");
  });
});
