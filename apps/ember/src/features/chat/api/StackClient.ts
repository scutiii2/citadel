import { apiRequest } from "../../../api/http";

/** One short fact in a chat's short-term memory. `source` is `user`, `agent` or `compaction` (a summary of older items). */
export interface StackItem {
  id: number;
  text: string;
  pinned: boolean;
  source: string;
  at: string;
}

/** A chat's stack and how full it is. `warn` is on from 80% (the server decides); `full` when no free slot is left. */
export interface StackView {
  items: StackItem[];
  used: number;
  limit: number;
  warn: boolean;
  full: boolean;
}

/** What compacting answers: `compacted` is false when there was nothing to replace. */
export interface CompactResult extends StackView {
  compacted: boolean;
  replaced: number;
}

const base = (chatId: string): string => `/api/chats/${encodeURIComponent(chatId)}/stack`;

export const stackClient = {
  view: (chatId: string) => apiRequest<StackView>("GET", base(chatId)),
  add: (chatId: string, text: string, pinned = false) => apiRequest<StackItem>("POST", `${base(chatId)}/items`, { text, pinned }),
  setPinned: (chatId: string, itemId: number, pinned: boolean) => apiRequest<StackItem>("PUT", `${base(chatId)}/items/${itemId}`, { pinned }),
  remove: (chatId: string, itemId: number) => apiRequest<void>("DELETE", `${base(chatId)}/items/${itemId}`),
  compact: (chatId: string) => apiRequest<CompactResult>("POST", `${base(chatId)}/compact`),
};
