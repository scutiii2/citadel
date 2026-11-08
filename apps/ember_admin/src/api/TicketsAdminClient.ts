import { apiRequest } from "./http";

export type TicketType = "bug" | "feature" | "other";
export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "low" | "normal" | "high" | "urgent";
export type TicketSource = "user" | "ai_user_request" | "ai_auto";

export interface TicketComment {
  id: number;
  ticket_id: number;
  author: string;
  author_role: "reporter" | "staff" | "ai";
  body: string;
  created_at: string;
}

export interface AdminTicket {
  id: number;
  group_id: number;
  type: TicketType;
  title: string;
  description: string;
  status: TicketStatus;
  /** The ticket's own priority; the group's can be higher. */
  priority: TicketPriority;
  /** The higher of the ticket's and its group's priority. */
  effective_priority: TicketPriority;
  assignee: string | null;
  reporter: string;
  source: TicketSource;
  tags: string[];
  /** `reported` came from the reporter or a model and is unverified; `verified` was added by ember_api. */
  context: { reported?: Record<string, string>; verified?: Record<string, string> };
  /** Laya was unsure whether this ticket belongs to that group. */
  possible_group_id: number | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  comments?: TicketComment[];
}

export interface TicketGroup {
  id: number;
  title: string;
  priority: TicketPriority;
  /** An admin set the priority by hand; automatic elevation is off. */
  priority_pinned: boolean;
  ticket_count: number;
  recent_count: number;
  open_count: number;
  last_activity: string;
  tags: string[];
}

export interface TicketFilters {
  status?: TicketStatus;
  type?: TicketType;
  tag?: string;
  priority?: TicketPriority;
  assignee?: string;
  group_id?: number;
  possible?: boolean;
  limit?: number;
}

/** An empty assignee clears it. */
export interface TicketChanges {
  status?: TicketStatus;
  priority?: TicketPriority;
  assignee?: string;
  tags?: string[];
}

/** A priority pins the group; pinned false hands it back to automatic elevation. */
export interface GroupChanges {
  priority?: TicketPriority;
  pinned?: boolean;
}

export interface TicketStats {
  open: number;
  urgent: number;
  groups: number;
}

function query(filters: TicketFilters = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === false || value === "") continue;
    params.set(key, String(value));
  }
  params.sort();
  const text = params.toString().replaceAll("+", "%20");
  return text ? `?${text}` : "";
}

export const ticketsAdminClient = {
  listGroups: async (filters: Pick<TicketFilters, "status" | "tag" | "priority"> = {}): Promise<TicketGroup[]> =>
    (await apiRequest<{ groups: TicketGroup[] }>("GET", `/api/admin/ticket-groups${query(filters)}`)).groups,
  listTickets: async (filters: TicketFilters = {}): Promise<AdminTicket[]> =>
    (await apiRequest<{ tickets: AdminTicket[] }>("GET", `/api/admin/tickets${query(filters)}`)).tickets,
  get: async (id: number): Promise<AdminTicket> =>
    (await apiRequest<{ ticket: AdminTicket }>("GET", `/api/admin/tickets/${id}`)).ticket,
  update: async (id: number, changes: TicketChanges): Promise<AdminTicket> =>
    (await apiRequest<{ ticket: AdminTicket }>("PATCH", `/api/admin/tickets/${id}`, changes)).ticket,
  comment: async (id: number, body: string): Promise<AdminTicket> =>
    (await apiRequest<{ ticket: AdminTicket }>("POST", `/api/admin/tickets/${id}/comments`, { body })).ticket,
  move: async (id: number, groupId: number | null): Promise<AdminTicket> =>
    (await apiRequest<{ ticket: AdminTicket }>("POST", `/api/admin/tickets/${id}/move`, { group_id: groupId })).ticket,
  updateGroup: async (id: number, changes: GroupChanges): Promise<TicketGroup> =>
    (await apiRequest<{ group: TicketGroup }>("PATCH", `/api/admin/ticket-groups/${id}`, changes)).group,
  stats: () => apiRequest<TicketStats>("GET", "/api/admin/tickets/stats"),
};
