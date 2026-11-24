import { apiRequest } from "../../../api/http";

export type FileSource = "manual" | "automatic" | "shared";

/** A file without its text, as the list and search routes answer. Times are naive UTC strings. */
export interface BrainFileRow {
  id: string;
  title: string;
  /** "" is the top level; otherwise up to three lowercase levels, "projects/citadel". */
  folder: string;
  tags: string[];
  /** manual: written by the user; automatic: written by an agent; shared: imported from another account. */
  source: FileSource;
  last_editor: "user" | "agent";
  /** Agents may edit this file (an automatic file is always editable by agents). */
  agent_editable: boolean;
  /** The user changed an agent's or a shared file; its original text can be restored. */
  edited: boolean;
  /** Counts every save. A save sends the one the editor opened so the server can refuse a stale one. */
  revision: number;
  created_at: string;
  updated_at: string;
  chars: number;
  /** Set on an agent-written file: editing it may break the agent that uses it. */
  warning: string | null;
  /** The sender's username on a shared file, else "". */
  shared_from: string;
}

/** One file with its text (the list rows carry `chars` instead). */
export interface BrainFile extends Omit<BrainFileRow, "chars"> {
  body: string;
}

export interface BrainList {
  files: BrainFileRow[];
  /** Every folder that holds a file, with its parents, sorted. */
  folders: string[];
}

export interface SearchHit extends BrainFileRow {
  score: number;
  snippet: string;
}

/** The account's use of its quota, with the live limits. */
export interface BrainSummary {
  files: number;
  bytes: number;
  /** Files in the folder that could not be read; they are not listed. */
  skipped: number;
  max_files: number;
  max_total_bytes: number;
  max_record_chars: number;
}

export interface FileDraft {
  title: string;
  body: string;
  tags: string[];
  folder: string;
}

/** A save sends only what changed. `agent_editable` is the switch for agents. */
export type FileChanges = Partial<FileDraft> & { agent_editable?: boolean };

// The limits the server enforces that do not change at run time (stronghold `brain/records.py`, `notes/store.py`).
export const FILE_TITLE_MAX = 200;
export const FILE_TAG_MAX = 30;
export const FILE_TAGS_MAX = 10;
export const FOLDER_DEPTH_MAX = 3;

const path = (id: string) => `/api/brain/files/${encodeURIComponent(id)}`;

/** Portcullis's /api/brain routes (chat.use), passed on to Stronghold. */
export const brainClient = {
  /** Newest first. */
  list: () => apiRequest<BrainList>("GET", "/api/brain/files"),
  get: (id: string) => apiRequest<BrainFile>("GET", path(id)),
  create: (draft: FileDraft) => apiRequest<BrainFile>("POST", "/api/brain/files", draft),
  /** With `expectedRevision` the server refuses with 412 when the file was saved since. */
  update: (id: string, changes: FileChanges, expectedRevision?: number) =>
    apiRequest<BrainFile>("PUT", path(id), expectedRevision === undefined ? changes : { ...changes, expected_revision: expectedRevision }),
  /** Puts back the text from before the user's first edit of an agent or shared file. */
  revert: (id: string, expectedRevision?: number) =>
    apiRequest<BrainFile>("POST", `${path(id)}/revert`, expectedRevision === undefined ? {} : { expected_revision: expectedRevision }),
  remove: (id: string) => apiRequest<void>("DELETE", path(id)),
  /** Keyword (BM25) search over titles, tags and text. */
  search: (query: string) => apiRequest<{ results: SearchHit[] }>("GET", `/api/brain/search?q=${encodeURIComponent(query)}`),
  summary: () => apiRequest<BrainSummary>("GET", "/api/brain/summary"),
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
    .slice(0, FILE_TAG_MAX);
}

/** A folder as typed, cleaned: lowercase, "/" between levels, spaces become "-", other characters go. */
export function normalizeFolder(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s*[\\/]\s*/g, "/")
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_/-]/g, "")
    .replace(/\/+/g, "/")
    .replace(/^\/+|\/+$/g, "");
}

const SEGMENT = /^[a-z0-9][a-z0-9_-]{0,39}$/;

/** Why a cleaned folder cannot be saved, or "" when it can. The server checks again and also refuses reserved names. */
export function folderProblem(folder: string): string {
  if (folder === "") return "";
  const levels = folder.split("/");
  if (levels.length > FOLDER_DEPTH_MAX || !levels.every((level) => SEGMENT.test(level))) {
    return `A folder is up to ${FOLDER_DEPTH_MAX} levels of lowercase letters, digits, - and _ (40 characters each, starting with a letter or digit).`;
  }
  return "";
}
