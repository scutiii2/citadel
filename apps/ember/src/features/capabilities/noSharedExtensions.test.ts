import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { useAuthStore } from "../../stores/auth";
import CapabilitiesView from "./views/CapabilitiesView.vue";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../../utils/server", async (original) => ({ ...(await original<typeof import("../../utils/server")>()), apiRequest: api.request }));

it("never asks for /api/extensions", async () => {
  api.request.mockResolvedValue([]);
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "t", email: "t@example.com", email_verified: true, roles: [], permissions: ["chat.use", "tools.view"] };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/capabilities", component: CapabilitiesView }] });
  await router.push("/capabilities");
  mount(CapabilitiesView, { global: { plugins: [pinia, router] } });
  await flushPromises();
  const paths = api.request.mock.calls.map((call) => String(call[1]));
  expect(paths.some((path) => path.startsWith("/api/extensions"))).toBe(false);
});
