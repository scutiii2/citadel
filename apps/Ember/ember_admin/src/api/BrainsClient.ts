import { apiRequest } from "./http";

export type BrainScope = "personal" | "instance";
export interface BrainConnection {
  id: string | null; scope: BrainScope; label: string; endpoint: string; folder: string;
  enabled: boolean; allow_write: boolean; credential_configured: boolean;
  revision: number; generation: string | null; status: string;
}
export interface BrainDestination {
  id: string | null; scope: BrainScope; label: string; folder: string; enabled: boolean;
  writable: boolean; revision: number; generation: string | null; status: string;
}
export interface ConnectionDraft {
  label: string; endpoint: string; folder: string; enabled: boolean; allow_write: boolean;
  expected_revision: number; api_key?: string;
}
export interface BrainResult {
  content?: string; message?: string; status?: string; index_status?: string; refreshing?: boolean;
  entries?: { path: string; kind: string }[];
  hits?: { path: string; heading: string; content: string; scope: BrainScope; connection_label: string; refresh_status: string }[];
  failures?: { scope: string; message: string }[];
}
export const brainsClient = {
  connection: (scope: BrainScope) => apiRequest<BrainConnection>("GET", `/api/brains/connections/${scope}`),
  save: (scope: BrainScope, draft: ConnectionDraft) => apiRequest<BrainConnection>("PUT", `/api/brains/connections/${scope}`, draft),
  test: (scope: BrainScope, draft: ConnectionDraft) => apiRequest<BrainResult>("POST", `/api/brains/connections/${scope}/test`, draft),
  destinations: () => apiRequest<BrainDestination[]>("GET", "/api/brains/destinations"),
  browse: (scope: BrainScope | "both", operation: "list" | "read" | "search" | "status", path = "", query = "") =>
    apiRequest<BrainResult>("POST", "/api/brains/browse", { scope, operation, path, query }),
};
