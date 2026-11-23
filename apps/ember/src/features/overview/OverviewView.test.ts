import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { commandsClient } from "../../api/tools/CommandsClient";
import { agentsClient } from "../agents/api/AgentsClient";
import { ticketsClient } from "../tickets/api/TicketsClient";
import { usageClient } from "../usage/api/UsageClient";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Account } from "../../api/auth/AuthClient";
import { NAV_PAGES } from "../../router/pages";
import { useAuthStore } from "../../stores/auth";
import OverviewView from "./OverviewView.vue";

function setup(permissions: string[], emailVerified = true) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  const account: Account = {
    id: 1, username: "ada", email: "ada@example.com", email_verified: emailVerified,
    roles: [], permissions,
  };
  auth.account = account;
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [...NAV_PAGES.map((p) => ({ path: p.to, component: { template: "<div />" } })),
      { path: "/account", component: { template: "<div />" } }],
  });
  const wrapper = mount(OverviewView, { global: { plugins: [pinia, router] } });
  return { wrapper, auth, router };
}

beforeEach(() => {
  vi.spyOn(ticketsClient, "unreadCount").mockResolvedValue(2);
  vi.spyOn(agentsClient, "list").mockResolvedValue([{ status: "running" }, { status: "offline" }] as never);
  vi.spyOn(commandsClient, "capabilities").mockResolvedValue([{ enabled: true }, { enabled: false }, { enabled: true }] as never);
  vi.spyOn(usageClient, "mine").mockResolvedValue({ report: { total_tokens: 1234 } } as never);
});

describe("OverviewView", () => {
  it("shows live counts only for permitted pages, and Unavailable when a count fails", async () => {
    vi.spyOn(agentsClient, "list").mockRejectedValue(new Error("down"));
    const { wrapper } = setup(["chat.use"]);
    await flushPromises();
    const tiles = wrapper.findAll(".tile").map((t) => t.text());
    expect(tiles).toEqual([
      expect.stringContaining("Agents running"), expect.stringContaining("Capabilities on"), expect.stringContaining("Tokens, last 7 days"),
    ]);
    expect(tiles[0]).toContain("Unavailable");
    expect(tiles[1]).toContain("2");
    expect(tiles[2]).toContain("1234");
  });

  it("only offers permitted pages, with real links and an account shortcut", async () => {
    const { wrapper, router } = setup(["chat.use", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage", "watchers.view"]);
    expect(wrapper.find(".primary").attributes("href")).toBe("/");
    expect(wrapper.findAll(".card").map((link) => link.attributes("href"))).toEqual([
      "/agents", "/capabilities", "/notes", "/skills", "/shares", "/global", "/generator", "/capabilities/pdf_merger", "/capabilities/media_downloader", "/usage", "/settings", "/account",
    ]);
    expect(wrapper.text()).toContain("Signed in as ada");
    await wrapper.find('.card[href="/capabilities"]').trigger("click");
    await router.isReady();
    expect(router.currentRoute.value.path).toBe("/capabilities");
  });

  it("hides chat and empty groups without permissions, while keeping Account", async () => {
    const { wrapper, auth } = setup([]);
    expect(wrapper.find(".hero").exists()).toBe(false);
    expect(wrapper.find("#monitor-heading").exists()).toBe(false);
    expect(wrapper.findAll(".card").map((link) => link.attributes("href"))).toEqual(["/account"]);
    auth.account = { ...auth.account!, permissions: ["traffic.view", "roles.manage"] };
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card").map((link) => link.attributes("href"))).toEqual([
      "/account", "http://localhost:26501/overview",
    ]);
    expect(wrapper.find(".hero").exists()).toBe(false);
    expect(wrapper.get(".admin-shortcut").attributes("target")).toBe("_blank");
    expect(wrapper.get(".admin-shortcut").attributes("rel")).toBe("noopener noreferrer");
  });

  it("does not offer permission-gated actions to unverified accounts", () => {
    const { wrapper } = setup(["chat.use", "tools.view", "traffic.view", "roles.manage", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"], false);
    expect(wrapper.find(".hero").exists()).toBe(false);
    expect(wrapper.findAll(".card").map((link) => link.attributes("href"))).toEqual(["/account"]);
  });
});

describe("pages hidden by the administrator", () => {
  it("leaves them out of the cards", async () => {
    const { wrapper } = setup(["chat.use"]);
    const { usePageVisibilityStore } = await import("../../stores/navigation/pageVisibility");
    usePageVisibilityStore().hidden = ["/usage"];
    await wrapper.vm.$nextTick();

    const hrefs = wrapper.findAll(".card").map((link) => link.attributes("href"));
    expect(hrefs).not.toContain("/usage");
    expect(hrefs).toContain("/agents");
  });
});
