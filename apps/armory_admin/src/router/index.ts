import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { resolveGuard } from "./guard";

declare module "vue-router" {
  interface RouteMeta {
    /** Reachable without logging in (login). */
    guestOnly?: boolean;
    /** The portcullis permission the page needs; a list = any one of them. */
    permission?: string | string[];
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/capabilities" },
    { path: "/capabilities", name: "capabilities", component: () => import("../views/CapabilitiesAdminView.vue"), meta: { permission: "capabilities.manage" } },
    { path: "/connections", alias: "/extensions", name: "connections", component: () => import("../views/ConnectionsView.vue"), meta: { permission: "extensions.manage" } },
    { path: "/brain", name: "brain", component: () => import("../views/BrainView.vue"), meta: { permission: "settings.manage" } },
    { path: "/tickets", name: "tickets", component: () => import("../views/TicketSettingsView.vue"), meta: { permission: "tickets.manage" } },
    { path: "/settings", name: "settings", component: () => import("../views/EnvironmentSettingsView.vue"), meta: { permission: "capabilities.manage" } },
    { path: "/limits", name: "limits", component: () => import("../views/LimitsView.vue"), meta: { permission: "capabilities.manage" } },
    { path: "/email", name: "email", component: () => import("../views/EmailSettingsView.vue"), meta: { permission: "capabilities.manage" } },
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { guestOnly: true } },
    { path: "/no-access", name: "no-access", component: () => import("../views/NoAccessView.vue") },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.ensureLoaded();
  return resolveGuard(
    { name: to.name, fullPath: to.fullPath, guestOnly: to.meta.guestOnly, permission: to.meta.permission },
    { signedIn: auth.account !== null, hasPermission: auth.hasPermission },
  );
});
