import { ref, type Ref } from "vue";
import { readStored, writeStored } from "../../../utils/browser/storage";

const STORAGE_KEY = "ember_web.chatSidebarCollapsed";

// Per-browser convenience: blocked storage just means "expanded".
/** Whether the chat page's conversation list is folded away, remembered per browser. */
export function useSidebarCollapse(): { collapsed: Ref<boolean>; toggle: () => void } {
  const collapsed = ref(readStored(STORAGE_KEY) === "1");
  function toggle(): void {
    collapsed.value = !collapsed.value;
    writeStored(STORAGE_KEY, collapsed.value ? "1" : "0");
  }
  return { collapsed, toggle };
}
