/** The pages of the Legion admin app, in nav order, with the portcullis permission each needs.
 * One list, so the nav, the router and the guard cannot drift. */
export interface LegionPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  permission: string;
}

export const LEGION_PAGES: LegionPage[] = [
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
    to: "/servers",
    label: "MCP servers",
    icon: ["M4 5h16v5H4zM4 14h16v5H4z", "M8 7.5h.01M8 16.5h.01"],
    permission: "agents.manage",
  },
  {
    to: "/tuning",
    label: "Tuning",
    icon: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3", "M1 14h6M9 8h6M17 16h6"],
    permission: "tuning.manage",
  },
];
