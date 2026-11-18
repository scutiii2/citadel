import { apiRequest } from "./http";

/** The ticket settings document Armory keeps; the elevation rules ride along untouched. */
export interface TicketSettings {
  tags: Record<string, string>;
  auto_hourly_cap: number;
  recent_hours: number;
  elevation: Record<string, { tickets: number; recent: number }>;
  laya: { min_confidence: number; candidates: number; timeout_seconds: number };
}

/** portcullis's /api/admin/ticket-settings (needs tickets.manage), passed on to Armory, which validates the whole document. */
export const ticketSettingsClient = {
  get: () => apiRequest<TicketSettings>("GET", "/api/admin/ticket-settings"),
  save: (changes: Partial<TicketSettings>) => apiRequest<TicketSettings>("PATCH", "/api/admin/ticket-settings", changes),
};
