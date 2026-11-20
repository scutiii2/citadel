import { defineStore } from "pinia";
import { reactive, watch } from "vue";
import { ApiError, isApiStatus } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { stackClient, type CompactResult, type StackView } from "../api/StackClient";

export interface StackEntry {
  status: "idle" | "loading" | "ready" | "missing" | "error";
  view: StackView | null;
  /** The last load or change that failed (shown beside the list). */
  error: string;
  /** The last refused add (shown beside the field). */
  addError: string;
  /** A change is waiting for the server. */
  pending: boolean;
  compacting: boolean;
  /** What the last compaction did. */
  notice: string;
}

const idle = (): StackEntry => ({ status: "idle", view: null, error: "", addError: "", pending: false, compacting: false, notice: "" });
const FAILED = "Memory is unavailable right now.";

const reason = (error: unknown): string => (error instanceof ApiError && error.message ? error.message : FAILED);

function noticeOf(result: CompactResult): string {
  if (!result.compacted) return "Nothing to compact.";
  return `Replaced ${result.replaced} ${result.replaced === 1 ? "item" : "items"} with a summary.`;
}

/** The active chat's short-term memory, as the server holds it. Items are private: an entry is dropped when its chat
 * is left, and a reply that arrives after that (or after a newer load) is ignored. */
export const useStackStore = defineStore("stack", () => {
  const entries = reactive(new Map<string, StackEntry>());
  const auth = useAuthStore();
  const latest = new Map<string, number>();
  let counter = 0;

  // Always return the reactive entry (`??=` would return the raw object the first time, and the identity checks below would fail).
  const own = (chatId: string): StackEntry => {
    if (!entries.has(chatId)) entries.set(chatId, idle());
    return entries.get(chatId)!;
  };
  const entry = (chatId: string): Readonly<StackEntry> => entries.get(chatId) ?? idle();

  async function load(chatId: string): Promise<void> {
    if (!auth.account) return;
    const current = own(chatId);
    const token = ++counter;
    latest.set(chatId, token);
    if (!current.view) current.status = "loading";
    try {
      const view = await stackClient.view(chatId);
      if (latest.get(chatId) !== token) return;
      Object.assign(current, { view, status: "ready", error: "" });
    } catch (error) {
      if (latest.get(chatId) !== token) return;
      if (isApiStatus(error, 404)) Object.assign(current, { view: null, status: "missing", error: "" });
      else Object.assign(current, { status: current.view ? "ready" : "error", error: reason(error) });
    }
  }

  async function change(chatId: string, work: () => Promise<unknown>, errorField: "error" | "addError"): Promise<boolean> {
    if (!auth.account) return false;
    const current = own(chatId);
    if (current.pending || current.compacting) return false;
    current.pending = true;
    current.notice = "";
    current[errorField] = "";
    try {
      await work();
      if (entries.get(chatId) !== current) return false;
      await load(chatId);
      return entries.get(chatId) === current;
    } catch (error) {
      if (entries.get(chatId) === current) current[errorField] = reason(error);
      return false;
    } finally {
      current.pending = false;
    }
  }

  function add(chatId: string, text: string): Promise<boolean> {
    return change(chatId, () => stackClient.add(chatId, text), "addError");
  }

  async function setPinned(chatId: string, itemId: number, pinned: boolean): Promise<void> {
    await change(chatId, () => stackClient.setPinned(chatId, itemId, pinned), "error");
  }

  async function remove(chatId: string, itemId: number): Promise<void> {
    await change(chatId, () => stackClient.remove(chatId, itemId), "error");
  }

  async function compact(chatId: string): Promise<void> {
    if (!auth.account) return;
    const current = own(chatId);
    if (current.pending || current.compacting) return;
    current.error = "";
    current.notice = "";
    current.compacting = true;
    try {
      const result = await stackClient.compact(chatId);
      if (entries.get(chatId) !== current) return;
      latest.set(chatId, ++counter); // this answer is newer than any load still on its way
      Object.assign(current, { view: result, status: "ready", notice: noticeOf(result) });
    } catch (error) {
      if (entries.get(chatId) === current) current.error = reason(error);
    } finally {
      current.compacting = false;
    }
  }

  function forget(chatId: string): void {
    entries.delete(chatId);
    latest.delete(chatId);
  }

  watch(() => auth.account?.id, () => {
    entries.clear();
    latest.clear();
  }, { flush: "sync" });

  return { entry, load, add, setPinned, remove, compact, forget };
});
