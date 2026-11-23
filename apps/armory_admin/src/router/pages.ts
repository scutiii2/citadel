/** The pages of the Armory Admin app, in nav order, with the portcullis permission each needs.
 * One list, so the nav, the router and the guard cannot drift. */
export interface ArmoryPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon. */
  icon: string[];
  /** The portcullis permission the page needs; a list = any one of them. */
  permission: string | string[];
}

export const ARMORY_PAGES: ArmoryPage[] = [
  { to: "/overview", label: "Overview", icon: ["m3 10 9-7 9 7v11h-7v-7h-4v7H3z"], permission: ["capabilities.manage", "tickets.manage"] },
  {
    to: "/capabilities",
    label: "Capabilities",
    icon: ["m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z", "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65", "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"],
    permission: "capabilities.manage",
  },
  {
    to: "/tickets",
    label: "Ticket settings",
    icon: ["M4 9V6h16v3a2 2 0 0 0 0 6v3H4v-3a2 2 0 0 0 0-6z", "M10 8v8"],
    permission: "tickets.manage",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: ["M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3", "M1 14h6M9 8h6M17 16h6"],
    permission: "capabilities.manage",
  },
  {
    to: "/limits",
    label: "Limits",
    icon: ["m12 14 4-4", "M3.34 19a10 10 0 1 1 17.32 0"],
    permission: "capabilities.manage",
  },
  {
    to: "/email",
    label: "Email",
    icon: ["M3 6h18v12H3z", "m3 7 9 6 9-6"],
    permission: "capabilities.manage",
  },
];

/** The heading the header shows for a route path. */
export const pageTitle = (path: string): string => ARMORY_PAGES.find((page) => page.to === path)?.label ?? "";
