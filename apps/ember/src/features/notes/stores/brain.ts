import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import {
  brainClient,
  type BrainFile,
  type BrainFileRow,
  type BrainSummary,
  type FileChanges,
  type FileDraft,
  type SearchHit,
} from "../api/BrainClient";

/** The account's long-term memory files as the server holds them: list, folders, quota and search results.
 * The text of a file is not kept here (the page asks for it when a file opens). Everything is private: it is
 * dropped by `forget()` and when the account changes, and a reply that arrives after that, or after a newer
 * request, is ignored. Changes show only after the server answered. */
export const useBrainStore = defineStore("brain", () => {
  const auth = useAuthStore();
  const status = ref<"idle" | "loading" | "ready" | "error">("idle");
  const error = ref("");
  const files = ref<BrainFileRow[]>([]);
  const folders = ref<string[]>([]);
  const summary = ref<BrainSummary | null>(null);
  const hits = ref<SearchHit[] | null>(null);
  const searching = ref(false);
  const searchError = ref("");
  let loads = 0;
  let searches = 0;
  let epoch = 0; // raised by forget(): a change that started before it must not write after it

  async function load(): Promise<void> {
    if (!auth.account) return;
    const run = ++loads;
    if (status.value !== "ready") status.value = "loading";
    try {
      const [list, totals] = await Promise.all([brainClient.list(), brainClient.summary().catch(() => null)]);
      if (run !== loads) return;
      files.value = list.files;
      folders.value = list.folders;
      if (totals) summary.value = totals;
      status.value = "ready";
      error.value = "";
    } catch (err) {
      if (run !== loads) return;
      error.value = errorMessage(err);
      status.value = status.value === "ready" ? "ready" : "error";
    }
  }

  async function search(query: string): Promise<void> {
    const text = query.trim();
    const run = ++searches;
    searchError.value = "";
    if (!text || !auth.account) {
      hits.value = null;
      searching.value = false;
      return;
    }
    searching.value = true;
    try {
      const found = await brainClient.search(text);
      if (run === searches) hits.value = found.results;
    } catch (err) {
      if (run === searches) {
        hits.value = null;
        searchError.value = errorMessage(err);
      }
    } finally {
      if (run === searches) searching.value = false;
    }
  }

  function clearSearch(): void {
    searches++;
    hits.value = null;
    searching.value = false;
    searchError.value = "";
  }

  /** The saved file as a list row, first in the list (it was just changed) and in the hits that show it. */
  function place(record: BrainFile): void {
    const row: BrainFileRow & { body?: string } = { ...record, chars: record.body.length };
    delete row.body;
    files.value = [row, ...files.value.filter((f) => f.id !== row.id)];
    if (hits.value) hits.value = hits.value.map((h) => (h.id === row.id ? { ...h, ...row } : h));
  }

  /** Runs a change. Errors go to the caller (a 412 means the file changed since it was opened). */
  async function change(work: () => Promise<BrainFile>): Promise<BrainFile> {
    const started = epoch;
    const record = await work();
    if (started === epoch) {
      place(record);
      await load();
    }
    return record;
  }

  const create = (draft: FileDraft) => change(() => brainClient.create(draft));
  const save = (id: string, changes: FileChanges, revision: number) => change(() => brainClient.update(id, changes, revision));
  const revert = (id: string, revision: number) => change(() => brainClient.revert(id, revision));

  async function remove(id: string): Promise<void> {
    const started = epoch;
    await brainClient.remove(id);
    if (started !== epoch) return;
    files.value = files.value.filter((f) => f.id !== id);
    if (hits.value) hits.value = hits.value.filter((h) => h.id !== id);
    await load();
  }

  function forget(): void {
    epoch++;
    loads++;
    searches++;
    status.value = "idle";
    error.value = "";
    files.value = [];
    folders.value = [];
    summary.value = null;
    hits.value = null;
    searching.value = false;
    searchError.value = "";
  }

  watch(() => auth.account?.id, forget, { flush: "sync" });

  return { status, error, files, folders, summary, hits, searching, searchError, load, search, clearSearch, create, save, revert, remove, forget };
});
