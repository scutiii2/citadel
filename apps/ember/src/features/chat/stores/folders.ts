import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { foldersClient, type ChatFolder } from "../api/FoldersClient";
import { isApiStatus } from "../../../api/http";
import { useAccountList } from "../composables/useAccountList";
import { useChatStore } from "./chat";

const byPosition = (a: ChatFolder, b: ChatFolder) => a.position - b.position || a.id - b.id;

/** The account's chat folders. Loaded on first use and dropped when the user
 * changes (same pattern as the templates store). create / rename / reorder /
 * remove throw ember_api's error message so the dialog that called them can
 * show it. Which chat sits in which folder lives on the chat (`folderId`), in
 * the chat store. */
export const useFoldersStore = defineStore("folders", () => {
  const moving = ref(false);
  const { items, loading, loadError, generation, ensureLoaded, reload } = useAccountList(
    () => foldersClient.list(),
    () => { moving.value = false; },
  );

  /** In display order. */
  const folders = computed(() => [...items.value].sort(byPosition));

  function upsert(folder: ChatFolder): void {
    items.value = [...items.value.filter((f) => f.id !== folder.id), folder];
  }

  async function create(name: string): Promise<ChatFolder> {
    const started = generation();
    const folder = await foldersClient.create(name);
    if (started === generation()) upsert(folder);
    return folder;
  }

  async function rename(id: number, name: string): Promise<ChatFolder> {
    const started = generation();
    const folder = await foldersClient.rename(id, name);
    if (started === generation()) upsert(folder);
    return folder;
  }

  async function reorder(id: number, position: number): Promise<ChatFolder> {
    const started = generation();
    const folder = await foldersClient.reorder(id, position);
    if (started === generation()) upsert(folder);
    return folder;
  }

  /** Reload every position after the server saves an adjacent move. */
  async function move(id: number, direction: "up" | "down"): Promise<void> {
    if (moving.value) return;
    const started = generation();
    moving.value = true;
    try {
      await foldersClient.move(id, direction);
      if (started === generation()) await reload();
    } finally {
      if (started === generation()) moving.value = false;
    }
  }

  /** Deletes the folder and, on the server, every chat in it; the chat store
   * then drops those chats from the screen. A folder that is already gone
   * (404, another tab) is treated as deleted. A 409 (a chat in it is
   * answering) leaves everything as it was and throws. */
  async function remove(id: number): Promise<void> {
    const started = generation();
    try {
      await foldersClient.remove(id);
    } catch (err) {
      if (!isApiStatus(err, 404)) throw err;
    }
    if (started !== generation()) return;
    items.value = items.value.filter((f) => f.id !== id);
    useChatStore().forgetFolder(id);
  }

  return { folders, loading, moving, loadError, ensureLoaded, reload, create, rename, reorder, move, remove };
});
