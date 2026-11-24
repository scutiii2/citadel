/** The pages of the admin app, in nav order, with the permission each needs
 * (a list: any one of them). One list, so the nav and the router cannot drift. */

export const CONFIG_ISSUES_ICON = ["M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z", "M12 9v4", "M12 17h.01"];

export interface AdminPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  permission: string | string[];
}

export const ADMIN_PERMISSIONS = ["accounts.view", "accounts.manage", "accounts.delete", "roles.view", "roles.manage", "roles.assign", "invites.manage", "settings.manage", "config.issues.view"];

/** Administration destinations share their permission rules with nested routes. */
export const ADMIN_SECTIONS: AdminPage[] = [
  { to: "/overview", label: "Overview", icon: ["m3 10 9-7 9 7v11h-7v-7h-4v7H3z"], permission: ADMIN_PERMISSIONS },
  { to: "/admin/accounts", label: "Users", icon: ["M3 21v-3a5 5 0 0 1 5-5h3a5 5 0 0 1 5 5v3M20 21v-3a5 5 0 0 0-3-4", "M13.5 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0"], permission: ["accounts.view", "accounts.manage", "accounts.delete", "roles.assign"] },
  { to: "/admin/roles", label: "Roles & permissions", icon: ["M12 3 3 7v5c0 5 5 8 9 10 4-2 9-5 9-10V7zM8 12l3 3 5-6"], permission: ["roles.view", "roles.manage", "roles.assign"] },
  { to: "/admin/invites", label: "Invites", icon: ["M3 5h18v14H3zM3 5l9 8 9-8"], permission: "invites.manage" },
  { to: "/admin/settings", label: "Workspace settings", icon: ["M4 6h3M11 6h9M4 12h9M17 12h3M4 18h5M13 18h7", "M11 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0M17 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0M13 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0"], permission: "settings.manage" },
];

/** The rail's default arrangement (before an account saves its own). The Overview
 * page is the wordmark, so it is not in this list. */
const DEFAULT_ORDER = [
  "/admin/roles",
  "/admin/accounts",
  "/admin/settings",
  "/admin/invites",
];
const defaultRank = (page: AdminPage): number => {
  const at = DEFAULT_ORDER.indexOf(page.to);
  return at < 0 ? DEFAULT_ORDER.length : at;
};

export const ADMIN_PAGES: AdminPage[] = [
  ...ADMIN_SECTIONS,
];

/** The same pages in the rail's default arrangement, for the rail, the Overview tiles and the
 * sidebar editor. The router keeps using ADMIN_PAGES, whose order picks the home page. */
export const ADMIN_NAV_PAGES: AdminPage[] = [...ADMIN_PAGES].sort((a, b) => defaultRank(a) - defaultRank(b));

const EXTRA_TITLES: Record<string, string> = { "/config-issues": "Config issues", "/profile": "Profile", "/settings": "Settings" };

/** The heading the header shows for a route path. */
export const pageTitle = (path: string): string => ADMIN_PAGES.find((page) => page.to === path)?.label ?? EXTRA_TITLES[path] ?? "";
