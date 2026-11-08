import { onBeforeUnmount, watch, type Ref } from "vue";

/** Calls `close` when a press lands outside `root` while `open` is true, for the
 * dropdowns that hide on a click anywhere else. The listener exists only while
 * open. `event` is the document event to listen to: "pointerdown" closes as the
 * press starts, "click" once it ends. */
export function useOutsideClose(
  root: Readonly<Ref<HTMLElement | null>>,
  open: Readonly<Ref<boolean>>,
  close: () => void,
  event: "pointerdown" | "click" = "pointerdown",
): void {
  const onOutside = (e: Event): void => {
    if (root.value && !root.value.contains(e.target as Node)) close();
  };
  const stop = watch(
    open,
    (isOpen) => {
      if (isOpen) document.addEventListener(event, onOutside);
      else document.removeEventListener(event, onOutside);
    },
    { immediate: true },
  );
  onBeforeUnmount(() => {
    stop();
    document.removeEventListener(event, onOutside);
  });
}
