import { apiRequest } from "./http";

/** Assistant memory is separate from private Notes. Dates include a UTC offset. */
export interface MemoryNote {
  id: number;
  text: string;
  created_at: string;
}

export const MEMORY_MAX = 200;
export const MEMORY_TEXT_MAX = 500;
const path = (id: number) => `/api/memory/${id}`;

export const memoryClient = {
  list: () => apiRequest<MemoryNote[]>("GET", "/api/memory"),
  create: (text: string) => apiRequest<MemoryNote>("POST", "/api/memory", { text }),
  update: (id: number, text: string, expectedText: string) =>
    apiRequest<MemoryNote>("PUT", path(id), { text, expected_text: expectedText }),
  remove: (id: number) => apiRequest<void>("DELETE", path(id)),
};
