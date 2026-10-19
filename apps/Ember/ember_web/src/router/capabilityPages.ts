/** Capability IDs, including legacy extension IDs, with native workspaces.
 * Keep these out of NAV_PAGES: their entry point is the Capabilities card. */
import type { RouteRecordRaw } from "vue-router";

interface CapabilityPage {
  to: string;
  permission: string;
  aliases?: string[];
  route?: RouteRecordRaw;
}

export const CAPABILITY_PAGES: Record<string, CapabilityPage> = {
  notes: { to: "/notes", permission: "chat.use" },
  memory: { to: "/memory", permission: "chat.use" },
  gen: { to: "/generator", permission: "tools.execute" },
  ticket: { to: "/tickets", permission: "tickets.create" },
  pdf: {
    to: "/capabilities/pdf_merger", permission: "tools.execute", aliases: ["pdf_merger"],
    route: { path: "/capabilities/pdf_merger", name: "pdf-merger", component: () => import("../views/PdfMergerView.vue") },
  },
  video: {
    to: "/capabilities/video_downloader", permission: "tools.execute", aliases: ["video_downloader"],
    route: { path: "/capabilities/video_downloader", name: "video-downloader", component: () => import("../views/VideoDownloaderView.vue") },
  },
};

export function dedicatedCapabilityPage(name: string): CapabilityPage | undefined {
  return CAPABILITY_PAGES[name] ?? Object.values(CAPABILITY_PAGES).find((page) => page.aliases?.includes(name));
}

/** Register before the generic route. Adding a workspace needs one entry above and its view. */
export const NATIVE_CAPABILITY_ROUTES: RouteRecordRaw[] = Object.entries(CAPABILITY_PAGES).flatMap(([capability, page]) =>
  page.route ? [{ ...page.route, meta: { permission: page.permission, capability } }] : [],
);
