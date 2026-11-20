import { apiRequest } from "../../../api/http";

export type ShareKind = "file" | "section" | "skill" | "stack_item";
export type ShareStatus = "pending" | "accepted" | "declined" | "revoked" | "rejected";

/** One share as the lists show it. The text is not in it. Times are `...Z` strings. */
export interface Share {
  id: string;
  kind: ShareKind;
  title: string;
  status: ShareStatus;
  /** The sender's username. */
  sender: string;
  /** The recipient's username, or "global brain". */
  recipient: string;
  created_at: string;
  decided_at: string | null;
  /** What the share became once accepted: a file id or a skill id. */
  result_id: string | null;
  chars: number;
}

/** One share with its text, for the person who sent or received it. The text is another account's: untrusted. */
export interface ShareDetail extends Share {
  body: string;
  skill: { when_to_use: string; steps: string; tools: string } | null;
  /** The server's sentence about untrusted text. */
  notice: string;
}

export interface Block {
  uid: string;
  username: string;
  created_at: string;
}

/** What is shared. */
export type ShareWhat =
  | { kind: "file"; file_id: string }
  | { kind: "section"; file_id: string; heading: string }
  | { kind: "skill"; skill_id: number }
  | { kind: "stack_item"; chat_id: string; item_id: number };

/** Who gets it: one account by username, or the global brain's review queue. */
export type Recipient = { recipient: string } | { to_global: true };

export type NewShare = ShareWhat & Recipient;

/** Where an accepted file lands. A skill takes only the title. */
export interface Landing {
  title?: string;
  folder?: string;
}

export const SHARE_NAME_MAX = 80;

const path = (id: string) => `/api/brain/shares/${encodeURIComponent(id)}`;

/** Portcullis's /api/brain/shares and /api/brain/blocks routes (chat.use), passed on to Stronghold. */
export const sharingClient = {
  create: (share: NewShare) => apiRequest<Share>("POST", "/api/brain/shares", share),
  /** Waiting for the person's answer, newest first. */
  inbox: async () => (await apiRequest<{ shares: Share[] }>("GET", "/api/brain/shares/inbox")).shares,
  /** Everything the person sent, newest first, with its status. */
  sent: async () => (await apiRequest<{ shares: Share[] }>("GET", "/api/brain/shares/sent")).shares,
  get: (id: string) => apiRequest<ShareDetail>("GET", path(id)),
  /** The sender takes a share back before it is decided. */
  revoke: (id: string) => apiRequest<Share>("DELETE", path(id)),
  accept: (id: string, landing: Landing = {}) => apiRequest<Share>("POST", `${path(id)}/accept`, landing),
  decline: (id: string) => apiRequest<Share>("POST", `${path(id)}/decline`),
  blocks: async () => (await apiRequest<{ blocks: Block[] }>("GET", "/api/brain/blocks")).blocks,
  /** Blocking also declines what that account already sent. */
  block: async (username: string) => (await apiRequest<{ blocks: Block[] }>("PUT", "/api/brain/blocks", { username })).blocks,
  unblock: (uid: string) => apiRequest<void>("DELETE", `/api/brain/blocks/${encodeURIComponent(uid)}`),
};
