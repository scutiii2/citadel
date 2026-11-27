import { apiRequest } from "./http";

export type WindowName = "six_hour" | "weekly";
export type ResetKind = WindowName | "both";

/** An unused free reset. Times are naive UTC. */
export interface FreeReset {
  id: string;
  kind: ResetKind;
  granted_at: string;
  expires_at: string | null;
}

/** A raise of the limits until `ends_at` (naive UTC). */
export interface LimitBoost {
  id: string;
  windows: WindowName[];
  percent: number;
  granted_at: string;
  ends_at: string;
}

export interface AccountAllowance {
  account_id: number;
  username: string;
  auto_use: boolean;
  resets: FreeReset[];
  boosts: LimitBoost[];
}

/** Every enabled account, or the ones named. */
export type Recipients = { all: true } | { account_ids: number[] };

export interface AllowanceResult {
  done: number;
  /** Usernames nothing was done for. */
  failed: string[];
}

const BASE = "/api/admin/usage-allowances";

/** portcullis's allowance routes (settings.manage). Send times as ISO text with a zone. */
export const usageAllowanceClient = {
  list: () => apiRequest<AccountAllowance[]>("GET", BASE),
  grant: (body: Recipients & { kind: ResetKind; count: number; expires_at?: string }) =>
    apiRequest<AllowanceResult>("POST", `${BASE}/resets`, body),
  clear: (body: Recipients & { windows: WindowName[] }) => apiRequest<AllowanceResult>("POST", `${BASE}/clear`, body),
  boost: (body: Recipients & { windows: WindowName[]; percent: number; ends_at: string }) =>
    apiRequest<AllowanceResult>("POST", `${BASE}/boosts`, body),
  removeReset: (accountId: number, id: string) => apiRequest<void>("DELETE", `${BASE}/${accountId}/resets/${id}`),
  removeBoost: (accountId: number, id: string) => apiRequest<void>("DELETE", `${BASE}/${accountId}/boosts/${id}`),
};
