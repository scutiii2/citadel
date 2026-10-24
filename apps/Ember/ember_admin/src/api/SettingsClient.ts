import { apiRequest } from "./http";

/** What the administrator has switched on for everyone (ember_api's /api/settings). */
export interface AppSettings {
  /** Every answer asks before each tool runs, and "allow for this chat" is not offered. */
  force_tool_approval: boolean;
  /** Calendar alert channels left on for everyone. */
  calendar_inapp: boolean;
  calendar_email: boolean;
  calendar_push: boolean;
}

export type SettingName = keyof AppSettings;

/** Pages hidden from every account's sidebar (route paths such as "/usage"). Nav only. */
export interface HiddenPages {
  hidden: string[];
}

export const settingsClient = {
  /** Any logged-in account may read these. */
  get: () => apiRequest<AppSettings>("GET", "/api/settings"),
  /** settings.manage only. */
  set: (name: SettingName, value: boolean) =>
    apiRequest<Partial<AppSettings>>("PUT", `/api/admin/settings/${name}`, { value }),
  /** Any logged-in account may read the hidden pages. */
  pages: () => apiRequest<HiddenPages>("GET", "/api/settings/pages"),
  /** settings.manage only. Replaces the list; ember_api refuses "/" and "/settings". */
  setPages: (hidden: string[]) => apiRequest<HiddenPages>("PUT", "/api/admin/settings/pages", { hidden }),
};
