import { apiRequest } from "./http";

/** Portcullis's policy settings as they apply from the next start (the values in use, with what was saved here on top). */
export interface AppConfig {
  session_hours: number;
  default_role: string;
  require_email_verification: boolean;
  rate_limit: { enabled: boolean; scope: "ip" | "account" | "both"; max_attempts: number; window_seconds: number; lockout_seconds: number };
  ip_filter: { allow_list: string[]; deny_list: string[] };
  headers: { enabled: boolean; hsts_max_age: number };
  fingerprint: { enabled: boolean; signals: string[] };
  backup: { enabled: boolean; keep: number; every_hours: number };
  /** Which settings were saved here; the rest are the defaults. */
  stored: string[];
}

export type AppConfigChanges = Record<string, unknown>;

/** Needs settings.manage. A group is merged into the current one; a null value goes back to the default. Used from the next start. */
export const appConfigClient = {
  get: () => apiRequest<AppConfig>("GET", "/api/admin/app-config"),
  save: (changes: AppConfigChanges) => apiRequest<AppConfig>("PUT", "/api/admin/app-config", changes),
};
