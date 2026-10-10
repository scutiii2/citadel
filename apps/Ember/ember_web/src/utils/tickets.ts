import type { TicketComment, TicketStatus, TicketType } from "../api/TicketsClient";

export const STATUS_LABELS: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

export const TYPE_LABELS: Record<TicketType, string> = { bug: "Bug", feature: "Feature", other: "Other" };

/** Stroked 24x24 icon path data per status: a status is never shown by color alone. */
export const STATUS_ICONS: Record<TicketStatus, string> = {
  open: "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  in_progress: "M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  resolved: "M20 6L9 17l-5-5",
  closed: "M8 12h8M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
};

export const COMMENT_ROLE_LABELS: Record<TicketComment["author_role"], string> = {
  reporter: "You",
  ai: "Assistant, for you",
  staff: "Support",
};

/** mcp_server times carry an offset ("+00:00"), so they parse as they are. */
export function formatTicketTime(iso: string): string {
  return new Date(iso).toLocaleString();
}
