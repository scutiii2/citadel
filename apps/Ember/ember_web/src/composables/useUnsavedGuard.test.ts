import { mount } from "@vue/test-utils";
import { afterEach, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { useUnsavedGuard } from "./useUnsavedGuard";

const dirty = ref(false);
const busy = ref(false);
let guard!: ReturnType<typeof useUnsavedGuard>;

const Page = defineComponent({
  setup() {
    guard = useUnsavedGuard({ dirty: () => dirty.value, busy: () => busy.value, allow: (to) => to.path === "/page/2" });
    return () => h("div");
  },
});
const Other = defineComponent({ render: () => h("span") });

async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/page", component: Page },
      { path: "/page/2", component: Page },
      { path: "/other", component: Other },
    ],
  });
  await router.push("/page");
  await router.isReady();
  const wrapper = mount({ render: () => h(RouterView) }, { global: { plugins: [router] } });
  return { router, wrapper };
}

afterEach(() => { dirty.value = false; busy.value = false; });

it("lets a clean page go", async () => {
  const { router } = await setup();
  await router.push("/other");
  expect(router.currentRoute.value.path).toBe("/other");
});

it("asks when dirty, stays on no and goes on yes", async () => {
  const { router } = await setup();
  dirty.value = true;
  const first = router.push("/other");
  await Promise.resolve();
  expect(guard.open.value).toBe(true);
  guard.answer(false);
  await first;
  expect(router.currentRoute.value.path).toBe("/page");
  expect(guard.open.value).toBe(false);

  const second = router.push("/other");
  await Promise.resolve();
  guard.answer(true);
  await second;
  expect(router.currentRoute.value.path).toBe("/other");
});

it("refuses to leave while busy and lets an allowed route through", async () => {
  const { router } = await setup();
  dirty.value = true;
  await router.push("/page/2");
  expect(router.currentRoute.value.path).toBe("/page/2");
  busy.value = true;
  await router.push("/other");
  expect(router.currentRoute.value.path).toBe("/page/2");
  expect(guard.open.value).toBe(false);
});

it("warns before the tab closes only with edits or a save running", async () => {
  await setup();
  const event = () => { const e = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; };
  expect(event()).toBe(false);
  dirty.value = true;
  expect(event()).toBe(true);
  dirty.value = false;
  busy.value = true;
  expect(event()).toBe(true);
});
