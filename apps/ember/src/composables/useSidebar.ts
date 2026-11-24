import { ref } from "vue";
import { readStored, writeStored } from "../utils/browser/storage";

const KEY = "ember.sidebar";
// Shared by the header toggle and the sidebar; a per-browser choice that survives blocked storage.
const expanded = ref(readStored(KEY) !== "collapsed");

/** The desktop sidebar's folded state: labeled when expanded, icon-only when collapsed. */
export function useSidebar(): { expanded: typeof expanded; toggle: () => void } {
  return {
    expanded,
    toggle() {
      expanded.value = !expanded.value;
      writeStored(KEY, expanded.value ? "expanded" : "collapsed");
    },
  };
}
