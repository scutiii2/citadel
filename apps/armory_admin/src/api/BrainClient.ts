import { apiRequest } from "./http";

export interface BrainConnection {
  label: string;
  endpoint: string;
  folder: string;
  enabled: boolean;
  allow_write: boolean;
  credential_configured: boolean;
  revision: number;
  status: string;
}

export interface ConnectionDraft {
  label: string;
  endpoint: string;
  folder: string;
  enabled: boolean;
  allow_write: boolean;
  expected_revision: number;
  api_key?: string;
}

interface BrainCheck {
  status?: string;
  message?: string;
  index_status?: string;
}

const path = "/api/admin/brain";

export const brainClient = {
  connection: () => apiRequest<BrainConnection>("GET", path),
  save: (draft: ConnectionDraft) => apiRequest<BrainConnection>("PUT", path, draft),
  test: (draft: ConnectionDraft) => apiRequest<BrainCheck>("POST", path + "/test", draft),
  status: () => apiRequest<BrainCheck>("GET", path + "/status"),
  disable: (expected_revision: number) =>
    apiRequest<BrainConnection>("POST", path + "/disable", { expected_revision }),
};
