import { apiRequest } from "./http";

export interface ToolOrigin { origin_id: string; origin: string | null; has_override: boolean; }

export interface ToolService {
  name: "bard" | "scribe" | "reader";
  label: string;
  enabled: boolean;
  service_id: string | null;
  has_token: boolean;
  origins: ToolOrigin[];
  ready: boolean;
  reason: string | null;
}

export interface OriginLookup {
  found: boolean;
  origin: string;
  path: string;
  origin_id: string | null;
  group: { service_id: string; name: string } | null;
}

/** `code` says why a failed test failed: an HTTP status (401, 503, ...) or SETUP, NET, TIME, GONE. */
export interface ToolTestResult { ok: boolean; message: string; code?: string; origins: { origin_id: string; ok: boolean; message: string; code?: string }[]; }

export interface ToolSaveBody {
  enabled?: boolean;
  /** Write-only: left out, the saved token stays. */
  token?: string;
  addresses?: { address: string; name?: string; header_value?: string }[];
}

/** portcullis's /api/admin/tool-services (needs tool_services.manage), passed on to Stronghold. No token is ever returned. */
export const toolServicesClient = {
  list: async () => (await apiRequest<{ services: ToolService[] }>("GET", "/api/admin/tool-services")).services,
  lookup: (address: string) => apiRequest<OriginLookup>("POST", "/api/admin/tool-services/lookup", { address }),
  save: (name: string, body: ToolSaveBody) => apiRequest<ToolService>("PUT", `/api/admin/tool-services/${encodeURIComponent(name)}`, body),
  clear: (name: string) => apiRequest<ToolService>("DELETE", `/api/admin/tool-services/${encodeURIComponent(name)}`),
  test: (name: string) => apiRequest<ToolTestResult>("POST", `/api/admin/tool-services/${encodeURIComponent(name)}/test`),
};
