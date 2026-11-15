import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { resolveGuard } from "./guard";
import { ANALYTICS_PERMISSIONS } from "./pages";

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
    { path: "/", redirect: "/usage" },
    { path: "/usage", name: "usage", component: () => import("../views/UsageView.vue"), meta: { permission: "usage.all.view" } },
    { path: "/analytics", name: "analytics", component: () => import("../views/AnalyticsView.vue"), meta: { permission: ANALYTICS_PERMISSIONS } },
    { path: "/tickets", name: "tickets", component: () => import("../views/TicketsAdminView.vue"), meta: { permission: "tickets.manage" } },
    { path: "/tuning", name: "tuning", component: () => import("../views/TuningAdminView.vue"), meta: { permission: "tuning.manage" } },
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
