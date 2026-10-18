/** The ember_web pages an administrator may hide from the sidebar, in sidebar order.
 * A copy of the hideable entries of NAV_PAGES in ember_web/src/router/pages.ts (ember_admin
 * cannot import it): update both together. Chat ("/") and Settings ("/settings") are not
 * listed because ember_api refuses to hide them. An id ember_web does not know is ignored there. */
export const EMBER_WEB_PAGES = [
  { id: "/capabilities", label: "Capabilities" },
  { id: "/agents", label: "Agents" },
  { id: "/usage", label: "Usage" },
  { id: "/tickets", label: "Tickets" },
] as const;

export type HideablePageId = (typeof EMBER_WEB_PAGES)[number]["id"];
