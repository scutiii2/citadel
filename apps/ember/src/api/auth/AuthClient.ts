import { apiRequest } from "../http";
import { isDesktop, setSessionToken } from "../../utils/server";

/** The logged-in account, as ember_api's /api/auth routes return it. */
export interface Account {
  id: number;
  username: string;
  email: string;
  email_verified: boolean;
  /** False when ember_api lets unverified accounts work. Absent counts as true. */
  email_verification_required?: boolean;
  /** The chat suggests the next prompt after each answer. Absent counts as true. */
  prompt_suggestions?: boolean;
  roles: string[];
  permissions: string[];
}

export interface RegisterResult {
  account: Account;
  /** False when SMTP failed; the account exists and resend can retry. */
  verification_email_sent: boolean;
  email_error: string | null;
}

export interface RegisterInput {
  username: string;
  email: string;
  password: string;
  invite_code: string;
}

export interface EmailChangeResult {
  /** Now unverified (unless the email didn't actually change). */
  account: Account;
  /** False when SMTP failed or nothing changed; resend can retry. */
  verification_email_sent: boolean;
  email_error: string | null;
}

/** A device the account logged in from (a fingerprint of browser and network). */
export interface KnownDevice {
  id: number;
  /** "Firefox on Windows" */
  label: string;
  user_agent: string;
  ip_subnet: string;
  first_seen_at: string;
  last_seen_at: string;
  /** The device this page runs on. */
  current: boolean;
}

/** ember_api's /api/auth and /api/account routes. Stateless; the auth store holds the account. */
export const authClient = {
  me: () => apiRequest<Account>("GET", "/api/auth/me"),
  /** In the Windows app the answer carries the session token (a bearer); the browser keeps using its cookie. */
  login: async (username: string, password: string): Promise<Account> => {
    const answer = await apiRequest<Account & { session_token?: string }>(
      "POST", "/api/auth/login", { username, password }, isDesktop() ? { "X-Ember-Client": "desktop" } : undefined);
    const { session_token: token, ...account } = answer;
    if (token) setSessionToken(token);
    return account;
  },
  logout: async (): Promise<void> => {
    try { await apiRequest<void>("POST", "/api/auth/logout"); } finally { setSessionToken(""); }
  },
  register: async (input: RegisterInput): Promise<RegisterResult> => {
    const result = await apiRequest<RegisterResult>("POST", "/api/auth/register", input);
    // Registering starts a cookie session, which the Windows app cannot use. Log in once to get its bearer token.
    if (isDesktop()) {
      try { await authClient.login(input.username, input.password); } catch { /* the user can log in by hand */ }
    }
    return result;
  },
  verifyEmail: (code: string) => apiRequest<Account>("POST", "/api/auth/verify-email", { code }),
  resendVerification: () => apiRequest<{ sent: boolean }>("POST", "/api/auth/verify-email/resend"),
  changeEmail: (current_password: string, email: string) =>
    apiRequest<EmailChangeResult>("POST", "/api/account/email", { current_password, email }),
  changePassword: (current_password: string, new_password: string) =>
    apiRequest<Account>("POST", "/api/account/password", { current_password, new_password }),
  setPreferences: (prefs: { prompt_suggestions: boolean }) =>
    apiRequest<Account>("PATCH", "/api/account/preferences", prefs),
  devices: () => apiRequest<KnownDevice[]>("GET", "/api/account/devices"),
  forgetDevice: (id: number) => apiRequest<void>("DELETE", `/api/account/devices/${id}`),
};
