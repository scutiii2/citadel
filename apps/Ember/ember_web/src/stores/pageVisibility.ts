import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { settingsClient } from "../api/SettingsClient";
import { useAuthStore } from "./auth";
import { canonicalPagePath } from "../utils/pagePaths";

/** Pages the administrator hid from every sidebar, kept in ember_api. Loaded at login and
 * dropped when the account changes. A failed load means "nothing hidden": the sidebar must
 * never lose a page just because this list could not be read. `ready` turns true once the
 * first load has settled, so the rail does not draw a page and then remove it. */
export const usePageVisibilityStore = defineStore("pageVisibility", () => {
  const auth = useAuthStore();

  const hidden = ref<string[]>([]);
  const ready = ref(false);
  // Bumped on every account change: answers for the previous account are ignored.
  let generation = 0;

  async function load(): Promise<void> {
    const started = generation;
    try {
      const loaded = await settingsClient.pages();
      if (started === generation) hidden.value = [...new Set(loaded.hidden.map(canonicalPagePath))];
    } catch {
      if (started === generation) hidden.value = [];
    } finally {
      if (started === generation) ready.value = true;
    }
  }

  watch(
    () => auth.account?.id ?? null,
    (id) => {
      generation += 1;
      hidden.value = [];
      ready.value = false;
      if (id !== null) void load();
    },
    { immediate: true },
  );

  return { hidden, ready, load };
});
