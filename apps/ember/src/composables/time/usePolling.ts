import { onMounted, onUnmounted } from "vue";

/** Calls `fn` every `intervalMs` while the tab is visible, and once when it becomes
 * visible again. Does not call it on mount: the caller loads first. Stops on unmount. */
export function usePolling(fn: () => void, intervalMs: number): void {
  let timer: ReturnType<typeof setInterval> | undefined;
  function stop(): void {
    clearInterval(timer);
    timer = undefined;
  }
  function onVisibility(): void {
    stop();
    if (document.hidden) return;
    fn();
    timer = setInterval(fn, intervalMs);
  }
  onMounted(() => {
    if (!document.hidden) timer = setInterval(fn, intervalMs);
    document.addEventListener("visibilitychange", onVisibility);
  });
  onUnmounted(() => {
    stop();
    document.removeEventListener("visibilitychange", onVisibility);
  });
}
