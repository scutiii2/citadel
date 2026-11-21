import { apiRequest } from "../../../api/http";

export type ProposalStatus = "pending" | "accepted" | "declined";

/** One suggestion as the list shows it. The text is not in it. Times are `...Z` strings. */
export interface Proposal {
  id: string;
  title: string;
  folder: string;
  tags: string[];
  /** The chat whose short-term memory the suggestion comes from. */
  chat_id: string;
  /** The short-term items it comes from; may be empty. */
  item_ids: number[];
  status: ProposalStatus;
  created_at: string;
  decided_at: string | null;
  /** The file id once kept. */
  result_id: string | null;
  chars: number;
}

/** One suggestion with its text. An agent wrote it: show it as plain text. */
export interface ProposalDetail extends Proposal {
  body: string;
  /** The server's sentence about who wrote it. */
  notice: string;
}

/** What the person changes when keeping. `remove_items` also removes the source items from short-term memory. */
export interface Landing {
  title?: string;
  folder?: string;
  remove_items?: boolean;
}

export interface AcceptedProposal extends Proposal {
  /** How many short-term items were removed. */
  removed: number;
}

const path = (id: string) => `/api/brain/proposals/${encodeURIComponent(id)}`;

/** Portcullis's /api/brain/proposals routes (chat.use), passed on to Stronghold. */
export const proposalsClient = {
  /** Waiting for the person's answer, newest first. */
  list: async () => (await apiRequest<{ proposals: Proposal[] }>("GET", "/api/brain/proposals")).proposals,
  get: (id: string) => apiRequest<ProposalDetail>("GET", path(id)),
  accept: (id: string, landing: Landing = {}) => apiRequest<AcceptedProposal>("POST", `${path(id)}/accept`, landing),
  decline: (id: string) => apiRequest<Proposal>("POST", `${path(id)}/decline`),
};
