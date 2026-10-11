import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, KeepAlive, ref } from "vue";
import { useGamesStore } from "../stores/games";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GamesClient } from "../api/GamesClient";
import { useAuthStore } from "../stores/auth";
import GamesView from "./GamesView.vue";
const game = { id: "ascension", name: "Ascension", description: "Collect Ascended", icon: "", version: "1", url: "http://localhost:8060" };
beforeEach(() => { setActivePinia(createPinia()); useAuthStore().account = { id: 1, username: "player", email: "p@example.com", email_verified: true, roles: [], permissions: [] }; });
afterEach(() => vi.restoreAllMocks());
it("shows filtered games, launches a stage and closes it", async () => {
  vi.spyOn(GamesClient.prototype, "list").mockResolvedValue([game]); vi.spyOn(GamesClient.prototype, "launch").mockResolvedValue({ url: game.url + "/#ticket=x" });
  const w = mount(GamesView); await flushPromises(); expect(w.text()).toContain("Collect Ascended");
  await w.find("button.play").trigger("click"); await flushPromises(); expect(w.find("iframe").exists()).toBe(true);
  await w.find("button.close-game").trigger("click"); expect(w.find("iframe").exists()).toBe(false); w.unmount();
});
it("shows the empty account state and inline request failures", async () => {
  vi.spyOn(GamesClient.prototype, "list").mockResolvedValueOnce([]).mockRejectedValueOnce(new Error("Offline"));
  const w = mount(GamesView); await flushPromises(); expect(w.text()).toContain("No games available for your account");
  await w.find("button.refresh").trigger("click"); await flushPromises(); expect(w.find("[role=alert]").text()).toContain("Offline"); w.unmount();
});

it("clears a spent launch ticket when a cached view is deactivated", async () => {
  vi.spyOn(GamesClient.prototype, "list").mockResolvedValue([game]);
  vi.spyOn(GamesClient.prototype, "launch").mockResolvedValue({ url: game.url + "/#ticket=spent" });
  const visible = ref(true);
  const shell = defineComponent({ setup: () => () => h(KeepAlive, {}, { default: () => visible.value ? h(GamesView) : h("p", "Away") }) });
  const w = mount(shell); await flushPromises(); await w.find("button.play").trigger("click"); await flushPromises();
  expect(useGamesStore().launchUrl).toContain("ticket=spent");
  visible.value = false; await flushPromises(); expect(useGamesStore().launchUrl).toBe("");
  visible.value = true; await flushPromises(); expect(w.find("iframe").exists()).toBe(false); expect(w.find("button.play").exists()).toBe(true); w.unmount();
});
