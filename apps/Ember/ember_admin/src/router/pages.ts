/** The pages of the admin app, in nav order, with the permission each needs
 * (a list: any one of them). One list, so the nav and the router cannot drift. */

// The Analytics page shows whichever log kinds these allow.
export const LOG_PERMISSIONS = ["logs.view", "logs.errors.view", "logs.chat.view"];
// ...and its Traffic tab needs traffic.view; any one of these opens the page.
export const ANALYTICS_PERMISSIONS = [...LOG_PERMISSIONS, "traffic.view"];

export const CONFIG_ISSUES_ICON = ["M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z", "M12 9v4", "M12 17h.01"];

export interface AdminPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  permission: string | string[];
}

export const ADMIN_PERMISSIONS = ["accounts.view", "accounts.manage", "accounts.delete", "roles.view", "roles.manage", "roles.assign", "invites.manage", "settings.manage", "capabilities.manage", "extensions.manage", "agents.manage", "tuning.manage", "tickets.manage", "usage.all.view", "config.issues.view", ...ANALYTICS_PERMISSIONS];

/** Administration destinations share their permission rules with nested routes. */
export const ADMIN_SECTIONS: AdminPage[] = [
  { to: "/overview", label: "Overview", icon: ["m3 10 9-7 9 7v11h-7v-7h-4v7H3z"], permission: ADMIN_PERMISSIONS },
  { to: "/admin/accounts", label: "Accounts", icon: ["M3 21v-3a5 5 0 0 1 5-5h3a5 5 0 0 1 5 5v3M20 21v-3a5 5 0 0 0-3-4", "M13.5 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0"], permission: ["accounts.view", "accounts.manage", "accounts.delete", "roles.assign"] },
  { to: "/admin/roles", label: "Roles & permissions", icon: ["M12 3 3 7v5c0 5 5 8 9 10 4-2 9-5 9-10V7zM8 12l3 3 5-6"], permission: ["roles.view", "roles.manage", "roles.assign"] },
  { to: "/admin/invites", label: "Invites", icon: ["M3 5h18v14H3zM3 5l9 8 9-8"], permission: "invites.manage" },
  { to: "/admin/settings", label: "Workspace settings", icon: ["M4 6h3M11 6h9M4 12h9M17 12h3M4 18h5M13 18h7", "M11 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0M17 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0M13 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0"], permission: "settings.manage" },
  { to: "/admin/tuning", label: "Tuning", icon: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3", "M1 14h6M9 8h6M17 16h6"], permission: "tuning.manage" },
];

/** The rail's default arrangement (before an account saves its own). The Overview
 * page is the wordmark, so it is not in this list. */
const DEFAULT_ORDER = [
  "/admin/roles",
  "/admin/accounts",
  "/capabilities",
  "/extensions",
  "/agents",
  "/analytics",
  "/usage",
  "/admin/settings",
  "/admin/tuning",
  "/admin/invites",
  "/tickets",
];
const defaultRank = (page: AdminPage): number => {
  const at = DEFAULT_ORDER.indexOf(page.to);
  return at < 0 ? DEFAULT_ORDER.length : at;
};

export const ADMIN_PAGES: AdminPage[] = [
  ...ADMIN_SECTIONS,
  { to: "/usage", label: "Usage", icon: ["M3 3v16a2 2 0 0 0 2 2h16", "M18 17V9", "M13 17V5", "M8 17v-3"], permission: "usage.all.view" },
  { to: "/capabilities", label: "Capabilities", icon: ["m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z", "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65", "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"], permission: "capabilities.manage" },
  { to: "/extensions", label: "Extensions", icon: ["M12 2v6", "M8 8h8v4a4 4 0 0 1-8 0z", "M12 16v6"], permission: "extensions.manage" },
  { to: "/agents", label: "Agents", icon: ["M12 8V4H8", "M4 8h16v12H4z", "M2 14h2M20 14h2M15 13v2M9 13v2"], permission: "agents.manage" },
  { to: "/tickets", label: "Tickets", icon: ["M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z", "M13 5v2", "M13 17v2", "M13 11v2"], permission: "tickets.manage" },
  { to: "/analytics", label: "Analytics", icon: ["M22 12h-4l-3 9L9 3l-3 9H2"], permission: ANALYTICS_PERMISSIONS },
];

/** The same pages in the rail's default arrangement, for the rail, the Overview tiles and the
 * sidebar editor. The router keeps using ADMIN_PAGES, whose order picks the home page. */
export const ADMIN_NAV_PAGES: AdminPage[] = [...ADMIN_PAGES].sort((a, b) => defaultRank(a) - defaultRank(b));
