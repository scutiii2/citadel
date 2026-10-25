import { apiRequest } from "../http";

/** The account's own Laya strategy for prompts sent straight to the Triage Assistant (ember_api's /api/account/triage-strategy). */
export interface TriageStrategyInfo {
  /** The account's choice; null follows the administrator's default. */
  value: string | null;
  /** The administrator's default; null when none is set. */
  default: string | null;
  /** The strategies the Laya service offers; empty while it cannot be reached. */
  strategies: string[];
}

export const triageStrategyClient = {
  get: () => apiRequest<TriageStrategyInfo>("GET", "/api/account/triage-strategy"),
  /** null goes back to the administrator's default. */
  save: (value: string | null) => apiRequest<TriageStrategyInfo>("PUT", "/api/account/triage-strategy", { value }),
};
