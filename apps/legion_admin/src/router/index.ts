import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { resolveGuard } from "./guard";

declare module "vue-router" {
  interface RouteMeta {
    /** Reachable without logging in (login). */
    guestOnly?: boolean;
    /** The portcullis permission the page needs. */
    permission?: string | string[];
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/overview" },
    { path: "/overview", name: "overview", component: () => import("../views/OverviewView.vue"), meta: { permission: ["agents.manage", "tuning.manage"] } },
    { path: "/agents", name: "agents", component: () => import("../views/AgentsAdminView.vue"), meta: { permission: "agents.manage" } },
    { path: "/connections", name: "connections", component: () => import("../views/ConnectionsView.vue"), meta: { permission: "agents.manage" } },
    { path: "/servers", name: "servers", redirect: (to) => ({ name: "connections", query: to.query, hash: "#mcp-servers" }) },
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
