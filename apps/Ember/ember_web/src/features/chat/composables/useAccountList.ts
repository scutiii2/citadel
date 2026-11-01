import { ref, watch, type Ref } from "vue";
import { errorMessage } from "../../../utils/errors";
import { useAuthStore } from "../../../stores/auth";

/** An account-scoped list for a store: loaded on first use and dropped when
 * the user changes. `generation()` is bumped on every account change; an
 * action that started under an earlier one must not touch the list when its
 * request returns. `onReset` clears the store's own state on that change. */
export function useAccountList<T>(fetch: () => Promise<T[]>, onReset?: () => void): {
  items: Ref<T[]>;
  loading: Ref<boolean>;
  loadError: Ref<string>;
  generation: () => number;
  ensureLoaded: () => Promise<void>;
  reload: () => Promise<void>;
} {
  const auth = useAuthStore();

  const items = ref<T[]>([]) as Ref<T[]>;
  const loading = ref(false);
  const loadError = ref("");
  let loaded = false;
  // The load in progress, so a second ask waits for it instead of returning early.
  let inflight: Promise<void> | null = null;
  let generation = 0;

  watch(
    () => (auth.hasPermission("chat.use") ? (auth.account?.id ?? null) : null),
    () => {
      generation += 1;
      items.value = [];
      loaded = false;
      inflight = null;
      loading.value = false;
      loadError.value = "";
      onReset?.();
    },
  );

  /** Loads the list once; a failed load can be retried by calling this again.
   * Asked while a load is running, it waits for that load. */
  function ensureLoaded(): Promise<void> {
    if (loaded || !auth.hasPermission("chat.use")) return Promise.resolve();
    if (inflight) return inflight;
    const started = generation;
    const run = reload().finally(() => {
      if (inflight === run && started === generation) inflight = null;
    });
    inflight = run;
    return run;
  }

  async function reload(): Promise<void> {
    const started = generation;
    loading.value = true;
    loadError.value = "";
    try {
      const list = await fetch();
      if (started !== generation) return;
      items.value = list;
      loaded = true;
    } catch (err) {
      if (started === generation) loadError.value = errorMessage(err);
    } finally {
      if (started === generation) loading.value = false;
    }
  }

  return { items, loading, loadError, generation: () => generation, ensureLoaded, reload };
}
