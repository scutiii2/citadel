import type { RouteLocationRaw } from "vue-router";
import { TREASURY_PAGES } from "./pages";

export interface GuardTarget {
  name?: string | symbol | null;
  fullPath: string;
  guestOnly?: boolean;
  permission?: string | string[];
}

function allowed(needed: string | string[], has: (name: string) => boolean): boolean {
  return Array.isArray(needed) ? needed.some(has) : has(needed);
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
  const home = TREASURY_PAGES.find((p) => allowed(p.permission, auth.hasPermission));
  const away: RouteLocationRaw = { path: home?.to ?? "/no-access" };
  if (to.guestOnly) return away;
  if (to.permission && !allowed(to.permission, auth.hasPermission)) return away;
  if (to.name === "no-access" && home) return away;
  return true;
}
