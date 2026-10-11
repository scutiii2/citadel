import { apiRequest } from "./http";

/** What the administrator has switched on for everyone (ember_api's /api/settings). */
export interface AppSettings {
  /** Every answer asks before each tool runs, and "allow for this chat" is not offered. */
  force_tool_approval: boolean;
}

/** Pages the administrator hid from every account's sidebar (route paths such as "/usage"). */
export interface HiddenPages {
  hidden: string[];
}

export const settingsClient = {
  /** Any logged-in account may read these. */
  get: () => apiRequest<AppSettings>("GET", "/api/settings"),
  /** The pages hidden from every sidebar. Hiding is nav-only: the pages still open by URL. */
  pages: () => apiRequest<HiddenPages>("GET", "/api/settings/pages"),
};
