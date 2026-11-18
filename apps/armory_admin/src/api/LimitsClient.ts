import { apiRequest } from "./http";

/** The caps and lifetimes of one capability. `stored` is true once an administrator changed anything from the defaults. */
export interface CapabilityLimits {
  file_ttl_hours: number;
  sweep_interval_minutes: number;
  download_link_minutes: number;
  mcp_wait_seconds?: number;
  limits: Record<string, number>;
  stored: boolean;
}

export type LimitsCapability = "pdf_merger" | "media_downloader";
export type LimitsView = Record<LimitsCapability, CapabilityLimits> & { applies?: string };

/** What one capability's save may carry: top-level numbers and a `limits` object of numbers. */
export type LimitsChanges = { [key: string]: number | Record<string, number> };

/** portcullis's /api/armory-tuning (needs capabilities.manage), passed on to Armory, which checks the whole result. */
export const limitsClient = {
  get: () => apiRequest<LimitsView>("GET", "/api/armory-tuning"),
  save: (name: LimitsCapability, changes: LimitsChanges) => apiRequest<LimitsView>("PUT", `/api/armory-tuning/${name}`, changes),
  /** Drops what was saved; the defaults apply again. */
  reset: (name: LimitsCapability) => apiRequest<LimitsView>("DELETE", `/api/armory-tuning/${name}`),
};
