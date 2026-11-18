import { apiRequest } from "./http";

/** Armory's SMTP settings. The password is write-only: reads carry `has_password` instead. */
export interface EmailSettings {
  configured: boolean;
  smtp_server?: string;
  smtp_port?: number | null;
  /** "starttls" | "ssl" | "none"; empty = chosen from the port. */
  security?: string;
  from?: string;
  to?: string[];
  allowed_recipient_domains?: string[];
  has_password?: boolean;
}

export type EmailChanges = Record<string, string | number | string[] | null>;

/** portcullis's /api/armory-email (needs capabilities.manage), passed on to Armory, which checks the whole result. */
export const emailSettingsClient = {
  get: () => apiRequest<EmailSettings>("GET", "/api/armory-email"),
  /** Only the fields given change; a null value removes one. Nothing is saved if the result is not usable. */
  save: (changes: EmailChanges) => apiRequest<EmailSettings>("PUT", "/api/armory-email", changes),
};
