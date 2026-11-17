/** The pages of the Treasury Admin app, in nav order, with the portcullis permission each needs.
 * One list, so the nav, the router and the guard cannot drift. */
export interface TreasuryPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  /** The portcullis permission the page needs; a list = any one of them. */
  permission: string | string[];
}

export const TREASURY_PAGES: TreasuryPage[] = [
  {
    to: "/instances",
    label: "Instances",
    icon: ["M3 5a9 3 0 1 0 18 0 9 3 0 1 0-18 0", "M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5", "M3 12c0 1.7 4 3 9 3s9-1.3 9-3"],
    permission: "settings.manage",
  },
  {
    to: "/connections",
    label: "Connections",
    icon: ["M9 17H7a5 5 0 0 1 0-10h2", "M15 7h2a5 5 0 0 1 0 10h-2", "M8 12h8"],
    permission: "settings.manage",
  },
];
