import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { ticketsClient } from "./TicketsClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);
const TICKET = { id: 7, type: "bug", title: "T", description: "D", status: "open", created_at: "x", updated_at: "x", closed_at: null };

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ticketsClient", () => {
  it("lists tickets, optionally by status, and unwraps the list", async () => {
    request.mockResolvedValue({ tickets: [TICKET] });

    expect(await ticketsClient.list()).toEqual([TICKET]);
    expect(request).toHaveBeenLastCalledWith("GET", "/api/tickets");
    await ticketsClient.list("in_progress");
    expect(request).toHaveBeenLastCalledWith("GET", "/api/tickets?status=in_progress");
  });

  it("gets, comments on and closes one ticket and unwraps it", async () => {
    request.mockResolvedValue({ ticket: TICKET });

    expect(await ticketsClient.get(7)).toEqual(TICKET);
    expect(request).toHaveBeenLastCalledWith("GET", "/api/tickets/7");
    await ticketsClient.comment(7, "log attached");
    expect(request).toHaveBeenLastCalledWith("POST", "/api/tickets/7/comments", { body: "log attached" });
    await ticketsClient.close(7);
    expect(request).toHaveBeenLastCalledWith("POST", "/api/tickets/7/close");
  });

  it("creates a ticket with only type, title and description", async () => {
    request.mockResolvedValue({ ticket: TICKET, duplicate: false, group_size: 1 });

    const created = await ticketsClient.create({ type: "feature", title: "Dark mode", description: "Please" });

    expect(created.ticket.id).toBe(7);
    expect(request).toHaveBeenLastCalledWith("POST", "/api/tickets", { type: "feature", title: "Dark mode", description: "Please" });
  });
});
