import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { expect, it } from "vitest";
import SupermarketView from "./SupermarketView.vue";

it("moves an old Supermarket view to the merged workspace, preserving search and tab", async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    {path:"/capabilities/supermarket",component:SupermarketView},
    {path:"/capabilities",component:{template:"<div/>"}},
  ]});
  await router.push('/capabilities/supermarket?tab=extensions&q=notes&state=disabled');
  const w=mount(SupermarketView,{global:{plugins:[router]}});
  await flushPromises();
  expect(router.currentRoute.value.path).toBe('/capabilities');
  expect(router.currentRoute.value.query).toEqual({tab:'extensions',q:'notes'});
  w.unmount();
});
