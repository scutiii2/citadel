// Legion tuning as Portcullis returns it (/api/admin/tuning).
import { apiRequest } from "./http";

/** legion's editable tuning as portcullis returns it (/api/admin/tuning). */
export interface TuningView {
  /** What config_tuning.json says (editable sections only). */
  defaults: Record<string, unknown>;
  /** What an admin changed: dotted path -> value. */
  overrides: Record<string, number | boolean | string>;
  /** The two merged; what the agents use. */
  effective: Record<string, unknown>;
}

/** Legion's daily counters (/api/admin/tuning/insights): `{date: {counter: value}}`, plus the budgets in force. */
export interface InsightsView {
  days: number;
  history: Record<string, Record<string, number>>;
  budgets: { turn_tokens: number; turn_seconds: number; daily_tokens_per_user: number; daily_tokens_per_agent: number };
}

export type TuningChanges = Record<string, number | boolean | string | null>;

export const tuningClient = {
  /** tuning.manage only. */
  get: () => apiRequest<TuningView>("GET", "/api/admin/tuning"),
  /** tuning.manage only. A null value puts a path back to the file's value. Nothing is saved if one change is refused. */
  /** tuning.manage only. The last `days` days (1 to 30) of counters. */
  insights: (days: number) => apiRequest<InsightsView>("GET", `/api/admin/tuning/insights?days=${days}`),
  save: (changes: TuningChanges) => apiRequest<TuningView>("PUT", "/api/admin/tuning", { changes }),
};
