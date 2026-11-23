import type { RouteLocationRaw } from "vue-router";
import { canOpen, LEGION_PAGES } from "./pages";

export interface GuardTarget {
  name?: string | symbol | null;
  fullPath: string;
  guestOnly?: boolean;
  permission?: string | string[];
}

export interface GuardAuth {
  signedIn: boolean;
  hasPermission(name: string): boolean;
}

/** UX gate only: portcullis enforces every permission itself. Admin-only means agents.manage. */
export function resolveGuard(to: GuardTarget, auth: GuardAuth): true | RouteLocationRaw {
  if (!auth.signedIn) {
    return to.guestOnly ? true : { name: "login", query: to.fullPath === "/" ? {} : { redirect: to.fullPath } };
  }
  const home = LEGION_PAGES.find((p) => canOpen(p.permission, auth.hasPermission));
  const away: RouteLocationRaw = { path: home?.to ?? "/no-access" };
  if (to.guestOnly) return away;
  if (to.permission && !canOpen(to.permission, auth.hasPermission)) return away;
  if (to.name === "no-access" && home) return away;
  return true;
}
