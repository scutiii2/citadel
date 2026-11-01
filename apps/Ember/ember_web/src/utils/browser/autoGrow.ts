import { watch, type Ref } from "vue";

/** Sizes a textarea to its content, so it grows as the text does. */
export function growToContent(area: HTMLTextAreaElement): void {
  area.style.height = "auto";
  area.style.height = `${area.scrollHeight}px`;
}

/** Regrows the textarea when its width changes, since wrapping changes the height. */
export function growOnResize(field: Ref<HTMLTextAreaElement | null>): void {
  watch(field, (area, _previous, onCleanup) => {
    if (!area || typeof ResizeObserver === "undefined") return;
    let width = 0;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry || entry.contentRect.width === width) return;
      width = entry.contentRect.width;
      growToContent(area);
    });
    observer.observe(area);
    onCleanup(() => observer.disconnect());
  });
}
