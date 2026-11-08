/** The pages of the Legion admin app, in nav order, with the ember_api permission each needs.
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
];
