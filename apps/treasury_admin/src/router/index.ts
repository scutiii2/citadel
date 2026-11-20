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
    { path: "/services", name: "services", component: () => import("../views/ServicesView.vue"), meta: { permission: "settings.manage" } },
    { path: "/", redirect: "/instances" },
    { path: "/instances", name: "instances", component: () => import("../views/InstancesView.vue"), meta: { permission: "settings.manage" } },
    { path: "/connections", name: "connections", component: () => import("../views/ConnectionsView.vue"), meta: { permission: "settings.manage" } },
    { path: "/outside", name: "outside", component: () => import("../views/OutsideView.vue"), meta: { permission: "settings.manage" } },
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
