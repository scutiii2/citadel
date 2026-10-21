/** The pages in the nav rail and on the Overview page, in that order, with
 * the permission each needs (a list: any one of them). One list, so the two
 * can't drift apart. */

/** Icons for the two tabs of the narrow-screen bar that are not in NAV_PAGES:
 * Overview (it is the wordmark on the rail) and the account's Profile page. */
export const OVERVIEW_ICON = ["M3 3h7v9H3z", "M14 3h7v5h-7z", "M14 12h7v9h-7z", "M3 16h7v5H3z"];
export const PROFILE_ICON = ["M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z"];

export interface NavPage {
  to: string;
  label: string;
  /** SVG path data (24x24, stroked) drawn as the page's icon in the nav rail. */
  icon: string[];
  /** One line for the Overview page. */
  description: string;
  permission: string | string[];
}

export const NAV_PAGES: NavPage[] = [
  { to: "/", label: "Chat", icon: ["M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"], description: "Ask an AI agent; it can use mcp_server's tools.", permission: "chat.use" },
  {
    to: "/capabilities",
    label: "Capabilities",
    icon: ["m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z", "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65", "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"],
    description: "What mcp_server offers: its capabilities and extensions (other MCP servers). Run their tools, read their resources, pick the extensions your chats may use.",
    permission: ["tools.view", "chat.use"],
  },
  {
    to: "/agents",
    label: "Agents",
    icon: ["M12 8V4H8", "M4 10a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z", "M2 14h2", "M20 14h2", "M15 13v2", "M9 13v2"],
    description: "The AI agents behind ember: which are running, which is the entry agent, and what each is for.",
    permission: "chat.use",
  },
  { to: "/usage", label: "Usage", icon: ["M3 3v16a2 2 0 0 0 2 2h16", "M18 17V9", "M13 17V5", "M8 17v-3"], description: "Token usage and limits.", permission: "chat.use" },
  {
    to: "/notes",
    label: "Notes",
    icon: ["M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z", "M14 2v6h6", "M16 13H8", "M16 17H8", "M10 9H8"],
    description: "Private notes, just for your account.",
    permission: "chat.use",
  },
  {
    to: "/memory",
    label: "Memory",
    icon: ["M12 18V5", "M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4", "M17.6 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.6 1.5 4 4 0 0 0-2.8 5.6 4 4 0 0 0 .6 6.9A4 4 0 0 0 12 20a4 4 0 0 0 7.8-1 4 4 0 0 0 .6-6.9 4 4 0 0 0-2.8-5.6"],
    description: "Review and manage the context Ember remembers about you.",
    permission: "chat.use",
  },
  { to: "/brains", label: "Brains", icon: ["M4 4h7v16H4z", "M13 4h7v16h-7z"], description: "Browse durable shared and personal knowledge.", permission: "" },
  {
    to: "/generator",
    label: "Generator",
    icon: ["M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"],
    description: "Make random passwords, passphrases, PINs and TOTP codes.",
    permission: "tools.execute",
  },
  {
    to: "/capabilities/pdf_merger",
    label: "PDF merger",
    icon: ["m8 6 4-4 4 4", "M12 2v10.3a4 4 0 0 1-1.172 2.872L4 22", "m20 22-5-5"],
    description: "Combine PDFs and images into one file; reorder, rotate and pick pages.",
    permission: "tools.execute",
  },
  {
    to: "/capabilities/video_downloader",
    label: "Media downloader",
    icon: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
    description: "Download videos, music and photos, including TikTok photo posts.",
    permission: "tools.execute",
  },
  {
    to: "/tickets",
    label: "Tickets",
    icon: ["M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z", "M13 5v2", "M13 17v2", "M13 11v2"],
    description: "Report a bug, suggest a feature or ask for help, and follow the answers.",
    permission: "tickets.create",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: [
      "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
      "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z",
    ],
    description: "Your chat and appearance preferences, with search and a reset for each; admins also set tool approval.",
    permission: "chat.use",
  },
];

/** Pages an administrator cannot hide from the sidebar: Chat is home and Settings holds the account's own preferences. */
export const PROTECTED_PAGES: readonly string[] = ["/", "/settings"];

/** The pages an account with these permissions may open, less the ones an administrator hid
 * for everyone (`hidden`; nav only, the pages still open by URL). */
export function visiblePages(hasPermission: (permission: string) => boolean, hidden: readonly string[] = []): NavPage[] {
  return NAV_PAGES.filter(
    (p) =>
      (PROTECTED_PAGES.includes(p.to) || !hidden.includes(p.to)) &&
      (Array.isArray(p.permission) ? p.permission.some(hasPermission) : hasPermission(p.permission)),
  );
}
