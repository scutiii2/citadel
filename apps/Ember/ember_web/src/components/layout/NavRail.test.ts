import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Account } from "../../api/auth/AuthClient";
import { authClient } from "../../api/auth/AuthClient";
import { navPreferencesClient, type NavPrefs } from "../../api/navigation/NavPreferencesClient";
import { settingsClient } from "../../api/navigation/SettingsClient";
import { NAV_PAGES } from "../../router/pages";
import { useAuthStore } from "../../stores/auth";
import NavRail from "./NavRail.vue";
import { ticketsClient } from "../../features/tickets/api/TicketsClient";
vi.mock("../../features/tickets/api/TicketsClient", () => ({ ticketsClient: { unreadCount: vi.fn(() => Promise.resolve(2)) } }));

vi.mock("../../api/auth/AuthClient", () => ({ authClient: { logout: vi.fn(() => Promise.resolve()) } }));
vi.mock("../../api/navigation/SettingsClient", () => ({ settingsClient: { get: vi.fn(), pages: vi.fn() } }));
vi.mock("../../api/navigation/NavPreferencesClient", () => ({
  navPreferencesClient: { get: vi.fn(() => Promise.resolve({ order: [], pinned: [], hidden: [] })) },
}));

const ACCOUNT: Account = {
  id: 1,
  username: "lex",
  email: "lex@example.com",
  email_verified: true,
  roles: [],
  permissions: ["chat.use", "tools.view", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"],
};

async function setup(account: Account | null) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.account = account;
  const stub = { template: "<div />" };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...NAV_PAGES.map((p) => ({ path: p.to === "/tickets" ? "/tickets/:id?" : p.to, component: stub })),
      { path: "/capabilities/:name", name: "capability-page", component: stub },
      { path: "/chat/:id", name: "chat-id", component: stub },
      { path: "/account", component: stub },
      { path: "/overview", component: stub },
      { path: "/login", name: "login", component: stub },
    ],
  });
  const wrapper = mount(NavRail, { global: { plugins: [pinia, router] } });
  await flushPromises(); // the arrangement loads first
  return { wrapper, router, auth };
}

const pageLinks = (wrapper: Awaited<ReturnType<typeof setup>>["wrapper"]) => wrapper.findAll("nav.pages a");
type Wrapper = Awaited<ReturnType<typeof setup>>["wrapper"];
async function openMenu(wrapper: Wrapper): Promise<void> {
  if (!wrapper.find(".menu").exists()) await wrapper.get("button.account").trigger("click");
  await flushPromises();
}
/** The linked rows of the account menu (its pages, then Profile), after opening it. */
async function footerLabels(wrapper: Wrapper): Promise<string[]> {
  await openMenu(wrapper);
  return wrapper.findAll(".menu a.row:not(.admin-link)").map((l) => l.text());
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(settingsClient.pages).mockResolvedValue({ hidden: [] });
});

describe("NavRail", () => {
  it("keeps Tickets selected while a deep link is open", async () => {
    const { wrapper, router } = await setup({ ...ACCOUNT, permissions: [...ACCOUNT.permissions, "tickets.create"] });
    await router.push("/tickets/7");
    await flushPromises();
    expect(wrapper.find('a[href="/tickets"]').classes()).toContain("current");
    wrapper.unmount();
  });
  it("shows an unread badge for tickets and resets it after logout", async () => {
    const { wrapper, auth } = await setup({ ...ACCOUNT, permissions: [...ACCOUNT.permissions, "tickets.create"] });
    expect(wrapper.find(".ticket-count").text()).toBe("2");
    expect(wrapper.find('a[href="/tickets"]').attributes("aria-label")).toBe("Tickets, 2 unread");
    expect(ticketsClient.unreadCount).toHaveBeenCalled();
    auth.account = null;
    await flushPromises();
    expect(wrapper.find(".ticket-count").exists()).toBe(false);
    wrapper.unmount();
  });
  it("shows one icon-only link per page the account may open", async () => {
    const { wrapper } = await setup(ACCOUNT);

    const links = pageLinks(wrapper);

    // Capabilities, Agents, Usage and Settings sit in the account menu.
    expect(links.map((l) => l.attributes("aria-label"))).toEqual(["Notes", "Memory", "Skills", "Brains", "Generator", "PDF merger", "Media downloader"]);
    for (const link of [...links, ...wrapper.findAll("nav.header a")]) {
      expect(link.text()).toBe("");
      expect(link.find("svg").exists()).toBe(true);
    }
  });

  it("names each page for the hover tooltip", async () => {
    const { wrapper } = await setup(ACCOUNT);

    const [notes] = pageLinks(wrapper);

    expect(notes!.attributes("data-label")).toBe("Notes");
    expect(notes!.attributes("href")).toBe("/notes");
  });

  it("puts Chat in the header under the wordmark, kept marked on a chat id", async () => {
    const { wrapper, router } = await setup(ACCOUNT);
    const chat = wrapper.get("nav.header a");

    expect(chat.attributes("data-label")).toBe("Chat");
    expect(chat.attributes("href")).toBe("/");
    expect(wrapper.get(".wordmark").element.compareDocumentPosition(chat.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(pageLinks(wrapper).map((l) => l.attributes("aria-label"))).not.toContain("Chat");

    await router.push("/chat/abc");
    await flushPromises();
    expect(chat.classes()).toContain("current");
  });

  it("marks the page being viewed", async () => {
    const { wrapper, router } = await setup(ACCOUNT);
    await router.push("/notes");
    await flushPromises();

    const current = pageLinks(wrapper).filter((l) => l.classes().includes("router-link-exact-active"));

    expect(current.map((l) => l.attributes("aria-label"))).toEqual(["Notes"]);
  });

  it("marks the page being viewed in the account menu", async () => {
    const { wrapper, router } = await setup(ACCOUNT);
    await router.push("/agents");
    await flushPromises();
    await openMenu(wrapper);

    const current = wrapper.findAll(".menu a.row").filter((l) => l.classes().includes("router-link-exact-active"));

    expect(current.map((l) => l.text())).toEqual(["Agents"]);
  });

  it("keeps Capabilities marked in the menu while one of its pages is open", async () => {
    const { wrapper, router } = await setup(ACCOUNT);
    await router.push("/capabilities/pdf");
    await flushPromises();
    await openMenu(wrapper);

    const current = wrapper.findAll(".menu a.row").filter((l) => l.classes().includes("current"));

    expect(current.map((l) => l.text())).toEqual(["Capabilities"]);
  });

  it("shows no pages while the email still has to be verified", async () => {
    const { wrapper } = await setup({ ...ACCOUNT, email_verified: false });

    expect(pageLinks(wrapper)).toHaveLength(0);
    expect(wrapper.find(".account").exists()).toBe(true);
  });

  it("shows no pages and no account controls to a visitor", async () => {
    const { wrapper } = await setup(null);

    expect(pageLinks(wrapper)).toHaveLength(0);
    expect(wrapper.find(".account").exists()).toBe(false);
    expect(wrapper.find("button.logout").exists()).toBe(false);
    expect(wrapper.find("button.theme").exists()).toBe(true);
  });

  describe("the narrow-screen tab bar", () => {
    const tabLinks = (wrapper: Awaited<ReturnType<typeof setup>>["wrapper"]) => wrapper.findAll("nav.tabs a");

    it("has five fixed tabs, Chat in the middle", async () => {
      const { wrapper } = await setup(ACCOUNT);

      const labels = tabLinks(wrapper).map((l) => l.attributes("aria-label"));

      expect(labels).toEqual(["Overview", "Capabilities", "Chat", "Usage", "Profile"]);
      expect(tabLinks(wrapper).map((l) => l.text())).toEqual(labels);
      expect(wrapper.find("nav.tabs a.chat").attributes("href")).toBe("/");
    });

    it("keeps keyboard navigation in visual order", async () => {
      const { wrapper } = await setup(ACCOUNT);

      expect(tabLinks(wrapper).map((l) => l.attributes("href"))).toEqual(["/overview", "/capabilities", "/", "/usage", "/account"]);
    });

    it("drops the tabs the account may not open but keeps Overview and Profile", async () => {
      const { wrapper } = await setup({ ...ACCOUNT, permissions: [] });

      expect(tabLinks(wrapper).map((l) => l.attributes("aria-label"))).toEqual(["Overview", "Profile"]);
    });

    it("keeps Chat marked while a chat is open by id", async () => {
      const { wrapper, router } = await setup(ACCOUNT);
      router.addRoute({ path: "/chat/:id", name: "chat-id", component: { template: "<div />" } });
      await router.push("/chat/7");
      await flushPromises();

      expect(wrapper.find("nav.tabs a.chat").classes()).toContain("current");
    });

    it("is absent for a visitor", async () => {
      const { wrapper } = await setup(null);

      expect(wrapper.find("nav.tabs").exists()).toBe(false);
    });
  });

  describe("the account's arrangement", () => {
    const arrangement = (prefs: NavPrefs) => vi.mocked(navPreferencesClient.get).mockResolvedValueOnce(prefs);
    const labels = (wrapper: Awaited<ReturnType<typeof setup>>["wrapper"]) => pageLinks(wrapper).map((l) => l.attributes("aria-label"));

    it("puts pinned pages first, then a divider, then the rest", async () => {
      arrangement({ order: ["/memory", "/notes"], pinned: ["/memory"], hidden: [] });
      const { wrapper } = await setup(ACCOUNT);

      expect(labels(wrapper)).toEqual(["Memory", "Notes", "Skills", "Brains", "Generator", "PDF merger", "Media downloader"]);
      expect(wrapper.findAll("nav .divider")).toHaveLength(1);
      expect(wrapper.find("nav.pages").element.children[1]!.classList.contains("divider")).toBe(true);
    });

    it("leaves hidden pages out", async () => {
      arrangement({ order: [], pinned: [], hidden: ["/memory", "/notes"] });
      const { wrapper } = await setup(ACCOUNT);

      expect(labels(wrapper)).toEqual(["Skills", "Brains", "Generator", "PDF merger", "Media downloader"]);
      expect(wrapper.find("nav .divider").exists()).toBe(false);
    });

    it("keeps the account menu pages out of the arrangement", async () => {
      arrangement({ order: ["/usage", "/settings"], pinned: ["/usage"], hidden: ["/settings", "/agents"] });
      const { wrapper } = await setup(ACCOUNT);

      expect(await footerLabels(wrapper)).toEqual(["Capabilities", "Agents", "Usage", "Settings", "Profile"]);
      expect(labels(wrapper)).not.toContain("Usage");
    });

    it("draws no pages until the arrangement has loaded", async () => {
      let release: (prefs: NavPrefs) => void = () => {};
      vi.mocked(navPreferencesClient.get).mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
      const { wrapper } = await setup(ACCOUNT);
      expect(pageLinks(wrapper)).toHaveLength(0);

      release({ order: [], pinned: [], hidden: [] });
      await flushPromises();

      expect(pageLinks(wrapper)).toHaveLength(7);
    });
  });

  it("opens an account menu with the email, Profile, theme and Log out, and closes it on Escape", async () => {
    const { wrapper } = await setup(ACCOUNT);
    const trigger = wrapper.get("button.account");
    expect(trigger.attributes("aria-label")).toContain("lex");
    expect(wrapper.find(".menu").exists()).toBe(false);

    await openMenu(wrapper);

    expect(wrapper.get(".menu .email").text()).toBe("lex@example.com");
    expect(wrapper.get('.menu a[href="/account"]').text()).toBe("Profile");
    expect(wrapper.get(".menu .theme-row").text()).toContain("Theme");
    await wrapper.get(".menu").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".menu").exists()).toBe(false);
  });

  it("logs out to the login page from the account menu", async () => {
    const { wrapper, router, auth } = await setup(ACCOUNT);
    await openMenu(wrapper);

    await wrapper.find("button.logout").trigger("click");
    await flushPromises();

    expect(authClient.logout).toHaveBeenCalled();
    expect(auth.account).toBeNull();
    expect(router.currentRoute.value.name).toBe("login");
  });
});

it("offers Ember Admin to delegated admins and hides it for members and unverified accounts", async () => {
  const { wrapper, auth } = await setup(ACCOUNT);
  await openMenu(wrapper);
  expect(wrapper.find(".admin-link").exists()).toBe(false);
  auth.account = { ...ACCOUNT, permissions: ["roles.view"] };
  await flushPromises();
  await openMenu(wrapper);
  expect(wrapper.get(".admin-link").attributes("href")).toBe("http://localhost:5176/overview");
  expect(wrapper.get(".admin-link").attributes("target")).toBe("_blank");
  expect(wrapper.get(".admin-link").attributes("rel")).toBe("noopener noreferrer");
  auth.account = { ...auth.account, email_verified: false };
  await flushPromises();
  await openMenu(wrapper);
  expect(wrapper.find(".admin-link").exists()).toBe(false);
});

describe("pages hidden by the administrator", () => {
  it("leaves them out of the rail, keeps the visible menu pages", async () => {
    vi.mocked(settingsClient.pages).mockResolvedValue({ hidden: ["/usage"] });
    const { wrapper } = await setup(ACCOUNT);

    expect(pageLinks(wrapper).map((l) => l.attributes("aria-label"))).toEqual(["Notes", "Memory", "Skills", "Brains", "Generator", "PDF merger", "Media downloader"]);
    expect(await footerLabels(wrapper)).toEqual(["Capabilities", "Agents", "Settings", "Profile"]);
  });

  it("never removes Chat or Settings, even if the list names them", async () => {
    vi.mocked(settingsClient.pages).mockResolvedValue({ hidden: ["/", "/settings"] });
    const { wrapper } = await setup(ACCOUNT);

    expect(wrapper.get("nav.header a").attributes("aria-label")).toBe("Chat");
    expect(await footerLabels(wrapper)).toContain("Settings");
  });

  it("draws no pages until the hidden list has loaded", async () => {
    let release: (value: { hidden: string[] }) => void = () => {};
    vi.mocked(settingsClient.pages).mockReturnValue(new Promise((resolve) => (release = resolve)));
    const { wrapper } = await setup(ACCOUNT);

    expect(pageLinks(wrapper)).toHaveLength(0);
    release({ hidden: [] });
    await flushPromises();
    expect(pageLinks(wrapper)).toHaveLength(7);
  });
});
