import { ref, type Ref } from "vue";

export interface ReorderOptions {
  /** Moves the item at `from` so it ends up at `to`. */
  move: (from: number, to: number) => void;
  /** How many items the list has now. */
  count: () => number;
  /** The Alt + arrow keys that move an item one step back and one step forward. */
  keys: { back: string; forward: string };
}

export interface Reorder {
  /** The index being dragged, for the `dragging` class; null when no drag is on. */
  dragFrom: Readonly<Ref<number | null>>;
  onDragStart: (index: number, event: DragEvent) => void;
  onDragEnd: () => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (index: number) => void;
  /** Alt + arrow moves a focused item; a key typed inside a child (e.g. a range input) is ignored. */
  onKey: (index: number, event: KeyboardEvent) => void;
}

/** Drag-and-drop and Alt + arrow reordering for a list of items, which the page binds to each item's
 * events. The caller supplies the move, so it works for any store. */
export function useReorder(options: ReorderOptions): Reorder {
  const dragFrom = ref<number | null>(null);

  function onDragStart(index: number, event: DragEvent): void {
    dragFrom.value = index;
    if (event.dataTransfer) {
      event.dataTransfer.setData("text/plain", String(index));
      event.dataTransfer.effectAllowed = "move";
    }
  }

  function onDragOver(event: DragEvent): void {
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  }

  function onDrop(index: number): void {
    if (dragFrom.value !== null) options.move(dragFrom.value, index);
    dragFrom.value = null;
  }

  function onKey(index: number, event: KeyboardEvent): void {
    if (event.target !== event.currentTarget) return;
    const { back, forward } = options.keys;
    if (!event.altKey || (event.key !== back && event.key !== forward)) return;
    event.preventDefault();
    const to = event.key === back ? index - 1 : index + 1;
    if (to >= 0 && to < options.count()) options.move(index, to);
  }

  return { dragFrom, onDragStart, onDragEnd: () => { dragFrom.value = null; }, onDragOver, onDrop, onKey };
}
