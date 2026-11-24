import { ref } from "vue";

// On wide screens the app header owns the Help button: a page's own help icon (the PanelHelp in its
// header actions) hands its text to that button instead of drawing a second icon.
const ready = ref(false); // the header is on screen (wide layout)
const count = ref(0); // page helps currently handed over
const open = ref(false);
const trigger = ref<HTMLElement | null>(null);

/** Shared state between the header's Help button and the page-level PanelHelp. */
export function useHeaderHelp() {
  return { ready, count, open, trigger };
}

/** Marks the header actions of a page: a PanelHelp inside may move to the header Help button. */
export const PAGE_ACTIONS_KEY = Symbol("page-actions");
