import { apiRequest } from "./http";

export type ForgeProvider = "claude" | "codex";
export type ForgeMode = "ask" | "accept_edits" | "plan" | "full_auto";

// The limits ember_api enforces (services/forge/groups.py, workers.py and routes/forge.py).
export const FORGE_TITLE_MAX = 80;
export const FORGE_MESSAGE_MAX = 8000;
export const FORGE_LABEL_MAX = 24;
export const FORGE_FOLDER_MAX = 500;

export interface ForgeWorker {
  id: number;
  provider: ForgeProvider;
  /** Its @mention handle. */
  label: string;
  reported_plan: string | null;
  online: boolean;
  eligible: boolean;
  /** Why it cannot be invited, when it is not eligible. */
  problem: string | null;
  last_seen: string | null;
  created_at: string;
}

/** The create response: the pairing token, shown once. */
export interface ForgeCreatedWorker extends ForgeWorker {
  token: string;
}

export interface ForgeMember {
  worker_id: number;
  label: string;
  provider: ForgeProvider;
  folder: string;
  online: boolean;
}

export interface ForgeGroup {
  id: number;
  title: string;
  mode: ForgeMode;
  relay: boolean;
  running: boolean;
  created_at: string;
  members: ForgeMember[];
}

export type ForgePlans = Record<ForgeProvider, string[]>;

export interface ForgeMessageEvent {
  type: "message";
  seq: number;
  /** "user", "system", or a worker id as text. */
  sender: string;
  kind: "text" | "tool" | "permission_request" | "permission_result" | "system";
  body: Record<string, unknown>;
  created_at: string;
}
export interface ForgeDeltaEvent {
  type: "delta";
  turn_id: string;
  sender: string;
  label: string;
  text: string;
}
export interface ForgeTurnEvent {
  type: "turn";
  running: boolean;
}
export interface ForgeLaggedEvent {
  type: "lagged";
}
export interface ForgePingEvent {
  type: "ping";
}
export type ForgeEvent = ForgeMessageEvent | ForgeDeltaEvent | ForgeTurnEvent | ForgeLaggedEvent | ForgePingEvent;

export interface ForgeGroupPatch {
  title?: string;
  mode?: ForgeMode;
  relay?: boolean;
  /** Required with mode "full_auto". */
  confirm_full_auto?: boolean;
}

const group = (id: number) => `/api/forge/groups/${id}`;

/** ember_api's /api/forge routes (forge.use; changing plan lists needs settings.manage). */
export const forgeClient = {
  plans: () => apiRequest<ForgePlans>("GET", "/api/forge/plans"),
  setPlans: (provider: ForgeProvider, plans: string[]) =>
    apiRequest<{ plans: string[] }>("PUT", `/api/forge/plans/${provider}`, { plans }),

  workers: () => apiRequest<ForgeWorker[]>("GET", "/api/forge/workers"),
  createWorker: (provider: ForgeProvider, label: string) =>
    apiRequest<ForgeCreatedWorker>("POST", "/api/forge/workers", { provider, label }),
  removeWorker: (id: number) => apiRequest<void>("DELETE", `/api/forge/workers/${id}`),

  groups: () => apiRequest<ForgeGroup[]>("GET", "/api/forge/groups"),
  createGroup: (title: string, mode: Exclude<ForgeMode, "full_auto">) =>
    apiRequest<ForgeGroup>("POST", "/api/forge/groups", { title, mode }),
  updateGroup: (id: number, patch: ForgeGroupPatch) => apiRequest<ForgeGroup>("PATCH", group(id), patch),
  removeGroup: (id: number) => apiRequest<void>("DELETE", group(id)),

  invite: (groupId: number, workerId: number, folder: string) =>
    apiRequest<ForgeGroup>("POST", `${group(groupId)}/workers`, { worker_id: workerId, folder }),
  setFolder: (groupId: number, workerId: number, folder: string) =>
    apiRequest<ForgeGroup>("PATCH", `${group(groupId)}/workers/${workerId}`, { folder }),
  /** Opens a folder dialog on the worker's own computer; resolves with the chosen path (null when cancelled). */
  browseFolder: (workerId: number, start: string | null) =>
    apiRequest<{ path: string | null }>("POST", `/api/forge/workers/${workerId}/browse`, { start: start || null }),
  removeMember: (groupId: number, workerId: number) =>
    apiRequest<ForgeGroup>("DELETE", `${group(groupId)}/workers/${workerId}`),

  send: (groupId: number, text: string) => apiRequest<ForgeMessageEvent>("POST", `${group(groupId)}/messages`, { text }),
  answerPermission: (groupId: number, requestId: string, allow: boolean) =>
    apiRequest<{ answered: boolean }>("POST", `${group(groupId)}/permissions/${requestId}`, { allow }),
  stop: (groupId: number) => apiRequest<{ stopping: boolean }>("POST", `${group(groupId)}/cancel`, {}),

  /** Server-sent events: stored messages after `after`, then live ones. */
  eventsUrl: (groupId: number, after: number) => `${group(groupId)}/events?after=${after}`,
};
