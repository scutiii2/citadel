/** The pages of the Legion admin app, in nav order, with the portcullis permission each needs.
 * One list, so the nav, the router and the guard cannot drift. */
export interface LegionPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  /** The portcullis permission the page needs; a list = any one of them. */
  permission: string | string[];
}

/** True when `has` grants the permission, or any one of a list. */
export const canOpen = (permission: string | string[], has: (name: string) => boolean): boolean => [permission].flat().some(has);

export const LEGION_PAGES: LegionPage[] = [
  {
    to: "/overview",
    label: "Overview",
    icon: ["M3 11 12 3l9 8", "M5 10v10h14V10", "M10 20v-6h4v6"],
    permission: ["agents.manage", "tuning.manage"],
  },
  {
    to: "/agents",
    label: "Agents",
    icon: ["M3 21v-3a5 5 0 0 1 5-5h3a5 5 0 0 1 5 5v3M20 21v-3a5 5 0 0 0-3-4", "M13.5 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0"],
    permission: "agents.manage",
  },
  {
    to: "/connections",
    label: "Connections",
    icon: ["M9 17H7a5 5 0 0 1 0-10h2", "M15 7h2a5 5 0 0 1 0 10h-2", "M8 12h8"],
    permission: "agents.manage",
  },
  {
    to: "/insights",
    label: "Insights",
    icon: ["M4 20V10M10 20V4M16 20v-8M22 20H2"],
    permission: "tuning.manage",
  },
  {
    to: "/tuning",
    label: "Tuning",
    icon: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3", "M1 14h6M9 8h6M17 16h6"],
    permission: "tuning.manage",
  },
];
