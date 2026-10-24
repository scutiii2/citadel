import { apiRequest } from "../../../api/http";

export type TicketType = "bug" | "feature" | "other";
export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";

export interface TicketComment {
  id: number;
  ticket_id: number;
  author: string;
  /** reporter = you, ai = the assistant writing for you, staff = support. */
  author_role: "reporter" | "staff" | "ai" | "system";
  body: string;
  created_at: string;
}

/** Only what a reporter may see: ember_api never sends tags, priority or other people's data here. */
export interface Ticket {
  has_unread?: boolean;
  id: number;
  type: TicketType;
  title: string;
  description: string;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  /** Present when one ticket is fetched. */
  comments?: TicketComment[];
}

export interface NewTicket {
  type: TicketType;
  title: string;
  description: string;
}

export interface CreatedTicket {
  ticket: Ticket;
  duplicate: boolean;
  group_size: number;
}

export const ticketsClient = {
  unreadCount: async (): Promise<number> => (await apiRequest<{ count: number }>("GET", "/api/tickets/unread-count")).count,
  list: async (status?: TicketStatus): Promise<Ticket[]> =>
    (await apiRequest<{ tickets: Ticket[] }>("GET", status ? `/api/tickets?status=${status}` : "/api/tickets")).tickets,
  get: async (id: number): Promise<Ticket> => (await apiRequest<{ ticket: Ticket }>("GET", `/api/tickets/${id}`)).ticket,
  create: (body: NewTicket) => apiRequest<CreatedTicket>("POST", "/api/tickets", body),
  comment: async (id: number, body: string): Promise<Ticket> =>
    (await apiRequest<{ ticket: Ticket }>("POST", `/api/tickets/${id}/comments`, { body })).ticket,
  close: async (id: number): Promise<Ticket> =>
    (await apiRequest<{ ticket: Ticket }>("POST", `/api/tickets/${id}/close`)).ticket,
  reopen: async (id: number): Promise<Ticket> =>
    (await apiRequest<{ ticket: Ticket }>("POST", `/api/tickets/${id}/reopen`)).ticket,
};
