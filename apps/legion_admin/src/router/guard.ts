import type { RouteLocationRaw } from "vue-router";
import { LEGION_PAGES } from "./pages";

export interface GuardTarget {
  name?: string | symbol | null;
  fullPath: string;
  guestOnly?: boolean;
  permission?: string;
}

export interface GuardAuth {
  signedIn: boolean;
  hasPermission(name: string): boolean;
}

/** UX gate only: ember_api enforces every permission itself. Admin-only means agents.manage. */
export function resolveGuard(to: GuardTarget, auth: GuardAuth): true | RouteLocationRaw {
  if (!auth.signedIn) {
    return to.guestOnly ? true : { name: "login", query: to.fullPath === "/" ? {} : { redirect: to.fullPath } };
  }
  const home = LEGION_PAGES.find((p) => auth.hasPermission(p.permission));
  const away: RouteLocationRaw = { path: home?.to ?? "/no-access" };
  if (to.guestOnly) return away;
  if (to.permission && !auth.hasPermission(to.permission)) return away;
  if (to.name === "no-access" && home) return away;
  return true;
}
