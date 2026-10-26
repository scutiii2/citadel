import { ref, type Ref } from "vue";
import { readStored, writeStored } from "../../../utils/browser/storage";
import { useAuthStore } from "../../../stores/auth";

const keyFor = (accountId: number) => `ember_web.collapsedFolders.${accountId}`;

// Per-browser convenience: damaged or blocked storage just means "all open".
function read(key: string): number[] {
  try {
    const parsed: unknown = JSON.parse(readStored(key) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is number => typeof v === "number") : [];
  } catch {
    return [];
  }
}

/** Which folders of the chat list are folded away, remembered per account in this browser. */
export function useFolderCollapse(): {
  collapsed: Ref<number[]>;
  isCollapsed: (id: number) => boolean;
  toggle: (id: number) => void;
} {
  const accountId = useAuthStore().account?.id;
  const key = accountId === undefined ? null : keyFor(accountId);
  const collapsed = ref<number[]>(key ? read(key) : []);

  function isCollapsed(id: number): boolean {
    return collapsed.value.includes(id);
  }

  function toggle(id: number): void {
    collapsed.value = isCollapsed(id) ? collapsed.value.filter((v) => v !== id) : [...collapsed.value, id];
    if (key) writeStored(key, JSON.stringify(collapsed.value));
  }

  return { collapsed, isCollapsed, toggle };
}
