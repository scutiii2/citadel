import { apiRequest } from "./http";

/** The Triage Assistant's default Laya strategy (ember_api's /api/admin/triage-strategy, settings.manage). */
export interface TriageStrategyInfo {
  /** The administrator's default; null means none is set and the voter settings choose. */
  default: string | null;
  /** The strategies the Laya service offers; empty while it cannot be reached. */
  strategies: string[];
}

export const triageStrategyClient = {
  get: () => apiRequest<TriageStrategyInfo>("GET", "/api/admin/triage-strategy"),
  /** null clears the default. */
  set: (value: string | null) => apiRequest<TriageStrategyInfo>("PUT", "/api/admin/triage-strategy", { value }),
};
