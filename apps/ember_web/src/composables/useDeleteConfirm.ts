import { ref, type Ref } from "vue";
import { errorMessage } from "../utils/errors";

/** The ask-then-confirm delete flow of a list page: `ask` opens the confirm modal for an
 * item, `confirm` calls `remove` and then `onGone`. `blocked` stops it while the page is busy. */
export function useDeleteConfirm<T>(
  remove: (item: T) => Promise<void>,
  onGone: (item: T) => void,
  blocked: () => boolean = () => false,
): {
  deleting: Ref<T | null>;
  removing: Ref<boolean>;
  removeError: Ref<string>;
  ask: (item: T) => void;
  confirm: () => Promise<void>;
} {
  const deleting = ref(null) as Ref<T | null>;
  const removing = ref(false);
  const removeError = ref("");

  function ask(item: T): void {
    if (removing.value || blocked()) return;
    deleting.value = item;
    removeError.value = "";
  }

  async function confirm(): Promise<void> {
    const item = deleting.value;
    if (item === null || removing.value || blocked()) return;
    removing.value = true;
    removeError.value = "";
    try {
      await remove(item);
      onGone(item);
      deleting.value = null;
    } catch (error) { removeError.value = errorMessage(error); }
    finally { removing.value = false; }
  }

  return { deleting, removing, removeError, ask, confirm };
}
