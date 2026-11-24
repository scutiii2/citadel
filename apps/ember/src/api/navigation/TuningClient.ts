// apps/Ember/ember_web/src/api/navigation/TuningClient.ts
import { apiRequest } from "../http";

/** The two caps a user may lower for their own answers. null = use the admin's value. */
export interface Limits {
  max_output_tokens: number | null;
  max_tool_rounds: number | null;
}

export interface AccountLimits {
  limits: Limits;
  /** The admin's current values: a user value above them is refused. null when the agents are unreachable. */
  ceiling: Limits;
}

/** ember_api's /api/account/tuning routes (any logged-in account). */
export const tuningClient = {
  get: () => apiRequest<AccountLimits>("GET", "/api/account/tuning"),
  save: (limits: Limits) => apiRequest<AccountLimits>("PUT", "/api/account/tuning", limits),
  reset: () => apiRequest<void>("DELETE", "/api/account/tuning"),
};
