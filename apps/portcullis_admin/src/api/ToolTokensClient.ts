import { apiRequest } from "./http";

/** One tool service as the card shows it. The token is never returned: `has_token` says one is in use,
 * `stored` that it was saved on this page (a token from the environment is not `stored`). */
export interface ToolService {
  name: string;
  label: string;
  has_token: boolean;
  stored: boolean;
}

/** `own`: Portcullis's tokens; `stronghold`: Stronghold's, passed on by Portcullis. */
export type ToolTokensKind = "own" | "stronghold";

const PATHS: Record<ToolTokensKind, string> = { own: "/api/admin/tool-tokens", stronghold: "/api/admin/stronghold-tool-tokens" };

/** Needs settings.manage. A null value removes the saved token; an environment token, if any, is used again. */
export const toolTokensClient = {
  list: async (kind: ToolTokensKind) => (await apiRequest<{ services: ToolService[] }>("GET", PATHS[kind])).services,
  save: async (kind: ToolTokensKind, changes: Record<string, string | null>) =>
    (await apiRequest<{ services: ToolService[] }>("PUT", PATHS[kind], changes)).services,
};
