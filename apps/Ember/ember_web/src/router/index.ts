import { createRouter, createWebHistory, type RouteLocationRaw } from "vue-router";
import { useAuthStore } from "../stores/auth";
import ChatView from "../views/ChatView.vue";
import { accountCapabilitiesClient } from "../api/AccountCapabilitiesClient";
import { commandsClient } from "../api/CommandsClient";
import { NATIVE_CAPABILITY_ROUTES } from "./capabilityPages";

declare module "vue-router" {
  interface RouteMeta {
    /** Reachable without logging in (login, register). */
    guestOnly?: boolean;
    /** Open to everyone, logged in or not, and left as it is: a shared chat. */
    public?: boolean;
    /** The ember_api permission the page needs; a list = any one of them. */
    permission?: string | string[];
    /** Open to any logged-in account, verified or not (the Account page,
     * so a mistyped email can be fixed). */
    anyAccount?: boolean;
    capability?: string;
  }
}

// Pages a logged-in, verified user may land on, in order of preference.
const HOME_PAGES: { name: string; permission: string }[] = [
  { name: "chat", permission: "chat.use" },
  { name: "capabilities", permission: "tools.view" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "chat", component: ChatView, meta: { permission: "chat.use" } },
    // The same page with one chat open; ChatView keeps the address and the open chat in step.
    { path: "/chat/:id", name: "chat-id", component: ChatView, meta: { permission: "chat.use" } },
    { path: "/brains", name: "brains", component: () => import("../views/BrainsView.vue") },
    // Lazy: each of these loads its own chunk only when first opened.
    { path: "/overview", name: "overview", component: () => import("../views/OverviewView.vue") },
    // The Tools page was merged into Capabilities; old links and bookmarks still work.
    { path: "/tools", redirect: (to) => ({ path: "/capabilities", query: to.query }) },
    {
      path: "/capabilities",
      name: "capabilities",
      component: () => import("../views/CapabilitiesView.vue"),
      // tools.view for the capabilities and tools, chat.use for switching extensions.
      meta: { permission: ["tools.view", "chat.use"] },
    },
    // Declared before /capabilities/:name so a capability named "supermarket" can never shadow it.
    {
      path: "/capabilities/supermarket",
      name: "supermarket",
      component: () => import("../views/SupermarketView.vue"),
      // tools.view for the built-in capabilities, chat.use for the extensions.
      meta: { permission: ["tools.view", "chat.use"] },
    },
    { path: "/capabilities/video_downloader", redirect: (to) => ({ path: "/capabilities/media_downloader", query: to.query, hash: to.hash }) },
    ...NATIVE_CAPABILITY_ROUTES,
    {
      path: "/capabilities/:name",
      name: "capability-page",
      component: () => import("../views/CapabilityPageView.vue"),
      meta: { permission: "tools.view" },
    },
    // The Extensions page was merged into Capabilities; old links and bookmarks still work.
    { path: "/extensions", redirect: (to) => ({ path: "/capabilities", query: to.query }) },
    // An extension no longer has a page of its own; its card on Capabilities has everything.
    { path: "/extensions/:id", redirect: "/capabilities" },
    {
      path: "/agents",
      name: "agents",
      component: () => import("../views/AgentsView.vue"),
      meta: { permission: "chat.use" },
    },
    {
      path: "/usage",
      name: "usage",
      component: () => import("../views/UsageView.vue"),
      meta: { permission: "chat.use" },
    },
    {
      path: "/notes",
      name: "notes",
      component: () => import("../views/NotesView.vue"),
      meta: { permission: "chat.use" },
    },
    {
      path: "/memory",
      name: "memory",
      component: () => import("../views/MemoryView.vue"),
      meta: { permission: "chat.use" },
    },
    {
      path: "/generator",
      name: "generator",
      component: () => import("../views/GeneratorView.vue"),
      meta: { permission: "tools.execute" },
    },
    {
      path: "/tickets/:id?",
      name: "tickets",
      component: () => import("../views/TicketsView.vue"),
      meta: { permission: "tickets.create" },
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsView.vue"),
      meta: { permission: "chat.use" },
    },
    {
      path: "/account",
      name: "account",
      component: () => import("../views/AccountView.vue"),
      meta: { anyAccount: true },
    },
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { guestOnly: true } },
    {
      path: "/register",
      name: "register",
      component: () => import("../views/RegisterView.vue"),
      meta: { guestOnly: true },
    },
    { path: "/verify-email", name: "verify-email", component: () => import("../views/VerifyEmailView.vue") },
    { path: "/no-access", name: "no-access", component: () => import("../views/NoAccessView.vue") },
    {
      path: "/shared/:token",
      name: "shared",
      component: () => import("../views/SharedChatView.vue"),
      meta: { public: true },
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

// Access rules. ember_api enforces every one of these itself; the guard only
// keeps the UI from showing pages whose calls would be refused.
router.beforeEach(async (to): Promise<true | RouteLocationRaw> => {
  // A shared chat is read by anyone holding the link: no login, and no
  // redirect for someone who is logged in either.
  if (to.meta.public) return true;
  const auth = useAuthStore();
  await auth.ensureLoaded();
  const account = auth.account;

  if (!account) {
    return to.meta.guestOnly ? true : { name: "login", query: to.fullPath === "/" ? {} : { redirect: to.fullPath } };
  }
  if (auth.needsVerification) {
    return to.name === "verify-email" || to.meta.anyAccount ? true : { name: "verify-email" };
  }

  const home = HOME_PAGES.find((p) => auth.hasPermission(p.permission));
  // The verify page stays open to an unverified account even when verification
  // is optional (the Account page links to it).
  if (to.meta.guestOnly || (to.name === "verify-email" && account.email_verified)) {
    return { name: home?.name ?? "no-access" };
  }
  const needed = to.meta.permission;
  if (needed && !(Array.isArray(needed) ? needed.some((p) => auth.hasPermission(p)) : auth.hasPermission(needed))) {
    return { name: home?.name ?? "no-access" };
  }
  if (to.name === "no-access" && home) return { name: home.name };
  if (to.meta.capability) {
    try {
      const [added, available] = await Promise.all([
        accountCapabilitiesClient.get(),
        // Execution access does not imply permission to browse the global catalog.
        // Native API routes always enforce the capability's current enabled state.
        auth.hasPermission("tools.view") ? commandsClient.capabilities() : null,
      ]);
      if (auth.account?.id !== account.id ||
          !added.capabilities.includes(to.meta.capability) ||
          (available !== null && !available.some((c) => c.name === to.meta.capability && c.enabled))) {
        return { name: home?.name ?? "no-access" };
      }
    } catch {
      return { name: home?.name ?? "no-access" };
    }
  }
  return true;
});
