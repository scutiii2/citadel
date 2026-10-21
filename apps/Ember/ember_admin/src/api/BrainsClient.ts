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

export interface PublicationReview {
  note_id: string; title: string; body: string; source_hash: string; source_revision: string; agent_readable: boolean;
}
export interface PromotionSuggestion {
  id: string; note_id: string; source_hash: string; source_revision: string; scope: BrainScope;
  destination_revision: number; generation: string; title: string; folder: string; tags: string[]; reason: string; draft: string;
}
export interface Publication {
  id: string; note_id: string; scope: BrainScope; path: string; status: string; source_changed?: boolean;
}
export const promotionsClient = {
  review: (id: string) => apiRequest<PublicationReview>("GET", `/api/brains/notes/${encodeURIComponent(id)}/review`),
  list: () => apiRequest<Publication[]>("GET", "/api/brains/promotions"),
  suggestions: () => apiRequest<PromotionSuggestion[]>("GET", "/api/brains/suggestions"),
  suggest: (note_ids: string[] = [], explicit_private: string[] = []) =>
    apiRequest<PromotionSuggestion[]>("POST", "/api/brains/suggestions/review", { note_ids, explicit_private }),
  dismiss: (id: string) => apiRequest("POST", `/api/brains/suggestions/${encodeURIComponent(id)}/dismiss`, {}),
  publish: (id: string, body: { source_hash: string; source_revision: string; scope: BrainScope; destination_revision: number;
    generation: string; path: string; draft: string; idempotency_key: string; shared_audience_reviewed: boolean }) =>
    apiRequest<Publication>("POST", `/api/brains/notes/${encodeURIComponent(id)}/promote`, body),
};
