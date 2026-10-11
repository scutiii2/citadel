import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import type { AdminTicket } from "../../api/TicketsAdminClient";
import TicketDrawer from "./TicketDrawer.vue";

const TICKET: AdminTicket = {
  id: 7,
  group_id: 3,
  type: "bug",
  title: "Email fails",
  description: "It does not send\nsecond line",
  status: "open",
  priority: "normal",
  effective_priority: "high",
  assignee: null,
  reporter: "alice",
  source: "ai_auto",
  tags: ["email", "config"],
  context: { reported: { tool_name: "tool_email_sendEmail", error_text: "not configured" }, verified: { account_id: "4" } },
  possible_group_id: null,
  created_at: "2026-10-10T10:00:00+00:00",
  updated_at: "2026-10-10T11:00:00+00:00",
  closed_at: null,
  comments: [{ id: 1, ticket_id: 7, author: "alice", author_role: "reporter", body: "Here is the log", created_at: "2026-10-10T12:00:00+00:00" }],
};

const mounted: ReturnType<typeof mount>[] = [];

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  document.body.innerHTML = "";
});

function drawer(extra: Partial<AdminTicket> = {}, props: { busy?: boolean; error?: string; notice?: string } = {}) {
  const wrapper = mount(TicketDrawer, { attachTo: document.body, props: { ticket: { ...TICKET, ...extra }, busy: false, error: "", notice: "", ...props } });
  mounted.push(wrapper);
  return wrapper;
}

describe("TicketDrawer", () => {
  it("shows the ticket, its source and its context as unverified text", () => {
    const text = drawer().text();

    expect(text).toContain("Email fails");
    expect(text).toContain("alice");
    expect(text).toContain("AI, automatic");
    expect(text).toContain("Priority: High");
    expect(text).toContain("Reported by the reporter or a model (unverified)");
    expect(text).toContain("tool_email_sendEmail");
    expect(text).toContain("Added by ember_api");
    expect(text).toContain("Here is the log");
  });

  it("emits a status change and puts the select back to the server value", async () => {
    const wrapper = drawer();
    const select = wrapper.find("select[aria-label='Status']");

    (select.element as HTMLSelectElement).value = "closed";
    await select.trigger("change");

    expect(wrapper.emitted("update")![0]).toEqual([{ status: "closed" }]);
    expect((select.element as HTMLSelectElement).value).toBe("open");
  });

  it("emits a priority change", async () => {
    const wrapper = drawer();
    const select = wrapper.find("select[aria-label='Priority']");

    (select.element as HTMLSelectElement).value = "urgent";
    await select.trigger("change");

    expect(wrapper.emitted("update")![0]).toEqual([{ priority: "urgent" }]);
    expect((select.element as HTMLSelectElement).value).toBe("normal");
    await wrapper.setProps({ ticket: { ...TICKET, priority: "urgent" } });
    expect((select.element as HTMLSelectElement).value).toBe("urgent");
  });

  it("saves the assignee, and an empty one clears it", async () => {
    const wrapper = drawer({ assignee: "root" });
    const input = wrapper.find("input[aria-label='Assignee']");

    await input.setValue("");
    await wrapper.find("button.save-assignee").trigger("click");

    expect(wrapper.emitted("update")![0]).toEqual([{ assignee: "" }]);
  });

  it("saves tags typed with commas", async () => {
    const wrapper = drawer();

    await wrapper.find("input[aria-label='Tags']").setValue(" auth, ui ,, ");
    await wrapper.find("button.save-tags").trigger("click");

    expect(wrapper.emitted("update")![0]).toEqual([{ tags: ["auth", "ui"] }]);
  });

  it("moves to a typed group, splits out, and offers the Laya hint", async () => {
    const wrapper = drawer({ possible_group_id: 5 });

    await wrapper.find("input[aria-label='Group number']").setValue("9");
    await wrapper.find("button.move").trigger("click");
    await wrapper.find("button.split").trigger("click");
    await wrapper.find("button.move-hint").trigger("click");

    expect(wrapper.emitted("move")).toEqual([[9], [null], [5]]);
    expect(wrapper.find("button.move-hint").text()).toContain("group 5");
  });

  it("does not offer the hint when there is none", () => {
    expect(drawer().find("button.move-hint").exists()).toBe(false);
  });

  it("sends a staff comment and clears the box only when the parent says the ticket changed", async () => {
    const wrapper = drawer();

    await wrapper.find("textarea[aria-label='Reply']").setValue("Looking into it");
    await wrapper.find("button.send-reply").trigger("click");

    expect(wrapper.emitted("comment")![0]).toEqual(["Looking into it"]);
    expect((wrapper.find("textarea[aria-label='Reply']").element as HTMLTextAreaElement).value).toBe("Looking into it");
    await wrapper.setProps({ replyReceipt: 1, ticket: { ...TICKET, comments: [...TICKET.comments!, { id: 2, ticket_id: 7, author: "root", author_role: "staff", body: "Looking into it", created_at: "2026-10-10T13:00:00+00:00" }] } });
    expect((wrapper.find("textarea[aria-label='Reply']").element as HTMLTextAreaElement).value).toBe("");
  });

  it("disables every control while busy and shows errors and notices", () => {
    const wrapper = drawer({}, { busy: true, error: "mcp_server is unreachable", notice: "Saved" });

    expect(wrapper.find("select[aria-label='Status']").attributes("disabled")).toBeDefined();
    expect(wrapper.find("button.send-reply").attributes("disabled")).toBeDefined();
    expect(wrapper.find(".error").text()).toBe("mcp_server is unreachable");
    expect(wrapper.find(".notice").text()).toBe("Saved");
  });

  it.each(["9suffix", "1.5", "1e2", "9007199254740993"])("does not move to an invalid group number: %s", async (value) => {
    const wrapper = drawer();
    await wrapper.find("input[aria-label='Group number']").setValue(value);
    expect(wrapper.find("button.move").attributes("disabled")).toBeDefined();
    await wrapper.find("button.move").trigger("click");
    expect(wrapper.emitted("move")).toBeUndefined();
  });
  it("keeps unsent fields when initial details or another edit refresh the ticket", async () => {
    const wrapper = drawer({ comments: undefined });
    await wrapper.find("input[aria-label='Assignee']").setValue("new owner");
    await wrapper.find("input[aria-label='Tags']").setValue("unsaved tag");
    await wrapper.find("textarea[aria-label='Reply']").setValue("unsent reply");
    await wrapper.setProps({ ticket: { ...TICKET } });
    expect((wrapper.find("input[aria-label='Assignee']").element as HTMLInputElement).value).toBe("new owner");
    expect((wrapper.find("input[aria-label='Tags']").element as HTMLInputElement).value).toBe("unsaved tag");
    expect((wrapper.find("textarea[aria-label='Reply']").element as HTMLTextAreaElement).value).toBe("unsent reply");
    await wrapper.setProps({ ticket: { ...TICKET, assignee: "new owner" } });
    expect((wrapper.find("input[aria-label='Tags']").element as HTMLInputElement).value).toBe("unsaved tag");
  });
});
