import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { resolveGuard } from "./guard";

declare module "vue-router" {
  interface RouteMeta {
    /** Reachable without logging in (login). */
    guestOnly?: boolean;
    /** The ember_api permission the page needs. */
    permission?: string;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/agents" },
    { path: "/agents", name: "agents", component: () => import("../views/AgentsAdminView.vue"), meta: { permission: "agents.manage" } },
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
