import { apiRequest } from "./http";

/** A private note, as ember_api stores it in db_gateway. Times are naive UTC. */
export interface Note {
  id: string;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
}

// The limits ember_api enforces (services/notes.py).
export const NOTE_TITLE_MAX = 200;
export const NOTE_BODY_MAX = 20_000;
export const NOTES_MAX = 200;

const path = (id: string) => `/api/notes/${encodeURIComponent(id)}`;

/** ember_api's /api/notes routes (chat.use). */
export const notesClient = {
  /** Most recently edited first. */
  list: () => apiRequest<Note[]>("GET", "/api/notes"),
  create: (title: string, body: string) => apiRequest<Note>("POST", "/api/notes", { title, body }),
  update: (id: string, title: string, body: string) => apiRequest<Note>("PUT", path(id), { title, body }),
  remove: (id: string) => apiRequest<void>("DELETE", path(id)),
};
