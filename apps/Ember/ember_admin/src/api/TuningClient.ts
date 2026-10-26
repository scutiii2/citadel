// apps/Ember/ember_admin/src/api/TuningClient.ts
import { apiRequest } from "./http";

/** garrison's editable tuning as ember_api returns it (/api/admin/tuning). */
export interface TuningView {
  /** What config_tuning.json says (editable sections only). */
  defaults: Record<string, unknown>;
  /** What an admin changed: dotted path -> value. */
  overrides: Record<string, number | boolean | string>;
  /** The two merged; what the agents use. */
  effective: Record<string, unknown>;
}

export type TuningChanges = Record<string, number | boolean | string | null>;

export const tuningClient = {
  /** tuning.manage only. */
  get: () => apiRequest<TuningView>("GET", "/api/admin/tuning"),
  /** tuning.manage only. A null value puts a path back to the file's value. Nothing is saved if one change is refused. */
  save: (changes: TuningChanges) => apiRequest<TuningView>("PUT", "/api/admin/tuning", { changes }),
};
