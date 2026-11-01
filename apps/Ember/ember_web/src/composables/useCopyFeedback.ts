import { onBeforeUnmount, ref, type Ref } from "vue";
import { copyText } from "../utils/browser/clipboard";

const COPIED_MS = 1500;

/** Copy-to-clipboard state for a button: `copied` for 1.5 s after a success,
 * `copyFailed` until the next try. */
export function useCopyFeedback(): { copied: Ref<boolean>; copyFailed: Ref<boolean>; copy: (text: string) => Promise<void> } {
  const copied = ref(false);
  const copyFailed = ref(false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  onBeforeUnmount(() => { disposed = true; clearTimeout(timer); });

  async function copy(text: string): Promise<void> {
    const ok = await copyText(text);
    if (disposed) return;
    clearTimeout(timer);
    copied.value = ok;
    copyFailed.value = !ok;
    if (ok) timer = setTimeout(() => (copied.value = false), COPIED_MS);
  }

  return { copied, copyFailed, copy };
}
