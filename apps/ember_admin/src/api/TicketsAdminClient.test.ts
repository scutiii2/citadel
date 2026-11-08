import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { ticketsAdminClient } from "./TicketsAdminClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ticketsAdminClient", () => {
  it("lists groups with only the filters that are set", async () => {
    request.mockResolvedValue({ groups: [{ id: 3 }] });

    expect(await ticketsAdminClient.listGroups()).toEqual([{ id: 3 }]);
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/ticket-groups");
    await ticketsAdminClient.listGroups({ status: "open", tag: "email", priority: undefined });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/ticket-groups?status=open&tag=email");
  });

  it("lists tickets by group, by possible duplicate, and encodes values", async () => {
    request.mockResolvedValue({ tickets: [] });

    await ticketsAdminClient.listTickets({ group_id: 3 });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/tickets?group_id=3");
    await ticketsAdminClient.listTickets({ possible: true, assignee: "a b" });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/tickets?assignee=a%20b&possible=true");
    await ticketsAdminClient.listTickets({ possible: false });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/tickets");
  });

  it("gets, updates, comments on and moves a ticket and unwraps it", async () => {
    request.mockResolvedValue({ ticket: { id: 7 } });

    expect(await ticketsAdminClient.get(7)).toEqual({ id: 7 });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/tickets/7");
    await ticketsAdminClient.update(7, { status: "closed", assignee: "" });
    expect(request).toHaveBeenLastCalledWith("PATCH", "/api/admin/tickets/7", { status: "closed", assignee: "" });
    await ticketsAdminClient.comment(7, "looking");
    expect(request).toHaveBeenLastCalledWith("POST", "/api/admin/tickets/7/comments", { body: "looking" });
    await ticketsAdminClient.move(7, null);
    expect(request).toHaveBeenLastCalledWith("POST", "/api/admin/tickets/7/move", { group_id: null });
  });

  it("changes a group's priority or pin and reads the stats", async () => {
    request.mockResolvedValue({ group: { id: 3, priority: "urgent" } });
    expect(await ticketsAdminClient.updateGroup(3, { priority: "urgent" })).toEqual({ id: 3, priority: "urgent" });
    expect(request).toHaveBeenLastCalledWith("PATCH", "/api/admin/ticket-groups/3", { priority: "urgent" });

    request.mockResolvedValue({ open: 2, urgent: 1, groups: 2 });
    expect(await ticketsAdminClient.stats()).toEqual({ open: 2, urgent: 1, groups: 2 });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/admin/tickets/stats");
  });
});
