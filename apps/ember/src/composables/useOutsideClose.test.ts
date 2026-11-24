import { mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { useOutsideClose } from "./useOutsideClose";

function host(event?: "pointerdown" | "click") {
  const open = ref(true);
  const close = vi.fn(() => { open.value = false; });
  const wrapper = mount(
    defineComponent({
      setup() {
        const root = ref<HTMLElement | null>(null);
        useOutsideClose(root, open, close, event);
        return () => h("div", { ref: root, id: "inside" }, [h("button", { id: "button" })]);
      },
    }),
    { attachTo: document.body },
  );
  return { wrapper, open, close };
}

afterEach(() => { document.body.innerHTML = ""; });

it("closes on a press outside and ignores one inside", () => {
  const { wrapper, close } = host();
  document.getElementById("button")!.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  expect(close).not.toHaveBeenCalled();
  document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  expect(close).toHaveBeenCalledOnce();
  wrapper.unmount();
});

it("listens to the chosen event only while open", async () => {
  const { wrapper, open, close } = host("click");
  document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  expect(close).not.toHaveBeenCalled();
  document.body.click();
  expect(close).toHaveBeenCalledOnce();
  await nextTick();
  document.body.click();
  expect(close).toHaveBeenCalledOnce();
  open.value = true;
  await nextTick();
  document.body.click();
  expect(close).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});

it("stops listening once unmounted", () => {
  const { wrapper, close } = host();
  wrapper.unmount();
  document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  expect(close).not.toHaveBeenCalled();
});
