import { apiRequest } from "./http";

/** The token limits (0 = unlimited) and the context cap Stronghold applies to every account. */
export interface UsageLimits {
  six_hour_token_limit: number;
  weekly_token_limit: number;
  max_context_tokens_per_chat: number;
  auto_summarize_ratio: number;
}

export interface ModelPrices {
  [model: string]: { input: number; output: number };
}

export interface UsageSettings {
  usage: UsageLimits;
  pricing: { currency: string; models: ModelPrices };
  /** Which part was changed from the defaults. */
  stored: { usage: boolean; pricing: boolean };
}

export interface UsageSettingsChanges {
  usage?: Partial<UsageLimits>;
  /** The whole price table: it replaces the saved one. */
  pricing?: { models: ModelPrices };
}

/** portcullis's /api/admin/stronghold-usage-settings (needs settings.manage), passed on to Stronghold, which checks every value. */
export const usageSettingsClient = {
  get: () => apiRequest<UsageSettings>("GET", "/api/admin/stronghold-usage-settings"),
  save: (changes: UsageSettingsChanges) => apiRequest<UsageSettings>("PUT", "/api/admin/stronghold-usage-settings", changes),
};
