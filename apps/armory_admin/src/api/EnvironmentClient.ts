import { apiRequest } from "./http";

/** One deployment value of Armory. A secret has `has_value` and never a `value`. */
export interface EnvironmentSetting {
  field: string;
  label: string;
  group: string;
  kind: "text" | "url" | "number" | "bool" | "path";
  help: string;
  secret: boolean;
  /** Used only after Armory restarts. */
  restart: boolean;
  /** Saved in Armory's database; false = the .env or default value is in use. */
  stored: boolean;
  value?: string | number | boolean;
  has_value?: boolean;
}

export interface EnvironmentView {
  settings: EnvironmentSetting[];
  /** Fields of the last change that Armory uses only after a restart. */
  restart?: string[];
}

export type EnvironmentChanges = Record<string, string | number | boolean | null>;

/** portcullis's /api/armory-environment (needs capabilities.manage), passed on to Armory, which checks every value. */
export const environmentClient = {
  get: () => apiRequest<EnvironmentView>("GET", "/api/armory-environment"),
  /** A null value puts the .env or default value back. Nothing is saved if one change is refused. */
  save: (changes: EnvironmentChanges) => apiRequest<EnvironmentView>("PUT", "/api/armory-environment", changes),
};
