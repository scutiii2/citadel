import { nextTick, ref, watch, type Ref } from "vue";

/** What a panel with its own draft and search needs besides the draft itself: a discard question, and focus
 * that returns to the panel's search when the Cancel and Save icons disappear. Copy kept in every admin app. */
export function useDraftPanel(dirty: Ref<boolean>, search: Ref<{ focus: () => void } | undefined>) {
  const discardOpen = ref(false);

  // The icons vanish when the draft becomes clean; if one had focus, hand it to search.
  watch(dirty, (now) => {
    if (!now && document.activeElement?.closest(".draft-actions")) void nextTick(() => search.value?.focus());
  });

  /** Runs a save and keeps keyboard focus on the panel when the control that had it goes away. */
  async function keepFocus(run: () => Promise<void>): Promise<void> {
    const hadFocus = !!document.activeElement?.closest(".draft-actions");
    await run();
    await nextTick();
    if (hadFocus && document.activeElement === document.body) search.value?.focus();
  }

  /** Closes the discard question; on yes drops the draft, then focuses search once the dialog has closed. */
  function answerDiscard(discard: boolean, drop: () => void): void {
    discardOpen.value = false;
    if (!discard) return;
    drop();
    void nextTick(async () => {
      await nextTick();
      search.value?.focus();
    });
  }

  return { discardOpen, keepFocus, answerDiscard };
}
