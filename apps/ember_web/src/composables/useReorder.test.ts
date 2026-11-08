import { expect, it, vi } from "vitest";
import { useReorder } from "./useReorder";

function setup() {
  const move = vi.fn();
  const reorder = useReorder({ move, count: () => 3, keys: { back: "ArrowUp", forward: "ArrowDown" } });
  return { move, reorder };
}

const key = (name: string, init: { altKey?: boolean; child?: boolean } = {}) => {
  const target = document.createElement("li");
  const event = new KeyboardEvent("keydown", { key: name, altKey: init.altKey ?? true, cancelable: true });
  Object.defineProperty(event, "target", { value: init.child ? document.createElement("input") : target });
  Object.defineProperty(event, "currentTarget", { value: target });
  return event;
};

it("moves the dragged item to the drop index and clears the drag", () => {
  const { move, reorder } = setup();
  const data = { setData: vi.fn(), effectAllowed: "" };
  reorder.onDragStart(2, { dataTransfer: data } as unknown as DragEvent);
  expect(reorder.dragFrom.value).toBe(2);
  expect(data.setData).toHaveBeenCalledWith("text/plain", "2");
  reorder.onDrop(0);
  expect(move).toHaveBeenCalledWith(2, 0);
  expect(reorder.dragFrom.value).toBeNull();
});

it("ignores a drop when nothing is being dragged, and clears on drag end", () => {
  const { move, reorder } = setup();
  reorder.onDrop(1);
  expect(move).not.toHaveBeenCalled();
  reorder.onDragStart(1, { dataTransfer: null } as unknown as DragEvent);
  reorder.onDragEnd();
  expect(reorder.dragFrom.value).toBeNull();
});

it("moves with Alt + arrow, within the list only", () => {
  const { move, reorder } = setup();
  const down = key("ArrowDown");
  reorder.onKey(0, down);
  expect(move).toHaveBeenCalledWith(0, 1);
  expect(down.defaultPrevented).toBe(true);
  reorder.onKey(0, key("ArrowUp"));
  reorder.onKey(2, key("ArrowDown"));
  expect(move).toHaveBeenCalledTimes(1);
});

it("ignores plain arrows, other keys and keys typed in a child", () => {
  const { move, reorder } = setup();
  reorder.onKey(1, key("ArrowDown", { altKey: false }));
  reorder.onKey(1, key("ArrowLeft"));
  reorder.onKey(1, key("ArrowDown", { child: true }));
  expect(move).not.toHaveBeenCalled();
});
