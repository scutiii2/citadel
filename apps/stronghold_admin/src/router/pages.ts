/** The pages of the Stronghold Admin app, in nav order, with the portcullis permission each needs.
 * One list, so the nav, the router and the guard cannot drift. */
export interface StrongholdPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  /** The portcullis permission the page needs; a list = any one of them. */
  permission: string | string[];
}

// The Analytics page shows whichever log kinds these allow.
export const LOG_PERMISSIONS = ["logs.view", "logs.errors.view", "logs.chat.view"];
// ...and its Traffic tab needs traffic.view; any one of these opens the page.
export const ANALYTICS_PERMISSIONS = [...LOG_PERMISSIONS, "traffic.view"];

export const STRONGHOLD_PAGES: StrongholdPage[] = [
  {
    to: "/usage",
    label: "Usage",
    icon: ["M3 3v16a2 2 0 0 0 2 2h16", "M18 17V9", "M13 17V5", "M8 17v-3"],
    permission: "usage.all.view",
  },
  {
    to: "/analytics",
    label: "Analytics",
    icon: ["M22 12h-4l-3 9L9 3l-3 9H2"],
    permission: "ANALYTICS_PERMISSIONS",
  },
  {
    to: "/tickets",
    label: "Tickets",
    icon: ["M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z", "M13 5v2", "M13 17v2", "M13 11v2"],
    permission: "tickets.manage",
  },
];
