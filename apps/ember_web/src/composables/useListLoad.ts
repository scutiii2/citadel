import { onMounted, ref, type Ref } from "vue";
import { errorMessage } from "../utils/errors";

/** A list loaded once on mount, with the loading and error state a page shows.
 * `load` runs it again (a retry button). */
export function useListLoad<T>(fetch: () => Promise<T[]>): {
  items: Ref<T[]>;
  loading: Ref<boolean>;
  loadError: Ref<string>;
  load: () => Promise<void>;
} {
  const items = ref<T[]>([]) as Ref<T[]>;
  const loading = ref(true);
  const loadError = ref("");

  async function load(): Promise<void> {
    loading.value = true;
    loadError.value = "";
    try { items.value = await fetch(); }
    catch (error) { loadError.value = errorMessage(error); }
    finally { loading.value = false; }
  }

  onMounted(load);
  return { items, loading, loadError, load };
}
