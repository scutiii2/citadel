import { apiRequest } from "./http";

/** A private note, as ember_api stores it in db_gateway. Times are naive UTC. */
export interface Note {
  id: string;
  title: string;
  body: string;
  tags: string[];
  /** The owner allows agents to read this note. */
  agent_readable: boolean;
  /** Who saved it last: the Notes page ("user") or an agent through mcp_server's notes tools. */
  last_editor: "user" | "agent";
  created_at: string;
  updated_at: string;
}

/** What a note's editor holds: everything a save replaces. */
export interface NoteDraft {
  title: string;
  body: string;
  tags: string[];
  agent_readable: boolean;
}

// The limits ember_api enforces (services/notes.py).
export const NOTE_TITLE_MAX = 200;
export const NOTE_BODY_MAX = 20_000;
export const NOTES_MAX = 200;
export const NOTE_TAG_MAX = 30;
export const NOTE_TAGS_MAX = 10;

/** Which of the account's existing tags Laya thinks fit a note. `skipped` tags were not
 * checked: past the per-request cap, or too much text for Laya to read. */
export interface TagSuggestions {
  suggested: string[];
  checked: number;
  skipped: number;
}

/** Up to three new tags the tag-writer agent proposes for a note. None are applied. */
export interface GeneratedTags {
  tags: string[];
}

const path = (id: string) => `/api/notes/${encodeURIComponent(id)}`;

/** ember_api's /api/notes routes (chat.use). */
export const notesClient = {
  /** Most recently edited first. */
  list: () => apiRequest<Note[]>("GET", "/api/notes"),
  create: (draft: NoteDraft) => apiRequest<Note>("POST", "/api/notes", draft),
  get: (id: string) => apiRequest<Note>("GET", path(id)),
  /** Replaces every field: leave one out and the server resets it. With `expectedUpdatedAt` (the
   * `updated_at` the editor opened) the server refuses with 412 when the note was saved since. */
  update: (id: string, draft: NoteDraft, expectedUpdatedAt?: string) =>
    apiRequest<Note>("PUT", path(id), expectedUpdatedAt === undefined ? draft : { ...draft, expected_updated_at: expectedUpdatedAt }),
  remove: (id: string) => apiRequest<void>("DELETE", path(id)),
  /** Asks Laya (a local model) about the note as the editor holds it, saved or not. */
  suggestTags: (draft: Pick<NoteDraft, "title" | "body" | "tags">) =>
    apiRequest<TagSuggestions>("POST", "/api/notes/suggest-tags", draft),
  /** Asks a light model (the tag-writer agent) for up to three new tags that fit the note. */
  generateTags: (draft: Pick<NoteDraft, "title" | "body" | "tags">) =>
    apiRequest<GeneratedTags>("POST", "/api/notes/generate-tag", draft),
};

/** A tag as the server keeps it: lowercase, spaces become "-", other characters go,
 * no leading "-" or "_", at most 30 characters. "" means nothing usable was left. */
export function normalizeTag(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/^[-_]+/, "")
    .slice(0, NOTE_TAG_MAX);
}
