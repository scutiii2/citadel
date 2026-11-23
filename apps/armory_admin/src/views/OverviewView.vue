<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";
import { capabilitiesAdminClient } from "../api/CapabilitiesAdminClient";
import { emailSettingsClient } from "../api/EmailSettingsClient";
import { environmentClient } from "../api/EnvironmentClient";
import { limitsClient } from "../api/LimitsClient";
import { ticketSettingsClient } from "../api/TicketSettingsClient";
import PanelHelp from "../components/admin/PanelHelp.vue";
import StatTile from "../components/admin/StatTile.vue";
import PageLayout from "../components/PageLayout.vue";
import { ARMORY_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { useNoticesStore } from "../stores/notices";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** The home page: live counts for what Armory holds, an alert while Armory does not answer, and shortcuts to each page.
 * A count that could not be loaded is "Unavailable", never zero. */
const auth = useAuthStore();
const notices = useNoticesStore();
const counts = reactive<Record<string, number | null>>({ capabilities: null, online: null, tickets: null, settings: null, limits: null, email: null });
const error = ref("");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const failed = (key: string) => !!error.value && counts[key] === null;
const may = (path: string) => ARMORY_PAGES.some((page) => page.to === path && [page.permission].flat().some(auth.hasPermission));

const tiles = computed(() => [
  { path: "/capabilities", key: "capabilities", label: "Capabilities", link: "Manage capabilities", icon: "m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83zM22 17.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65M22 12.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" },
  { path: "/tickets", key: "tickets", label: "Ticket tags", link: "Ticket settings", icon: "M4 9V6h16v3a2 2 0 0 0 0 6v3H4v-3a2 2 0 0 0 0-6zM10 8v8" },
  { path: "/settings", key: "settings", label: "Changed values", link: "Open settings", icon: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" },
  { path: "/limits", key: "limits", label: "Changed limits", link: "Open limits", icon: "m12 14 4-4M3.34 19a10 10 0 1 1 17.32 0" },
  { path: "/email", key: "email", label: "Email recipients", link: "Open email", icon: "M3 6h18v12H3zM3 7l9 6 9-6" },
].filter((tile) => may(tile.path)));

const descriptions: Record<string, string> = {
  "/capabilities": "Switch capabilities online or offline and see their tools.",
  "/tickets": "Ticket tags, caps and the Laya matching settings.",
  "/settings": "Armory's deployment values.",
  "/limits": "File lifetimes and caps of the PDF merger and media downloader.",
  "/email": "The mail account Armory sends through.",
};
function detail(path: string): string {
  if (path === "/capabilities" && counts.capabilities !== null) return `${counts.online ?? 0} of ${counts.capabilities} ${counts.capabilities === 1 ? "capability" : "capabilities"} online`;
  if (path === "/tickets" && counts.tickets !== null) return plural(counts.tickets, "tag");
  if (path === "/settings" && counts.settings !== null) return `${counts.settings} changed`;
  if (path === "/limits" && counts.limits !== null) return `${counts.limits} changed`;
  if (path === "/email" && counts.email !== null) return plural(counts.email, "recipient");
  return "";
}
const destinations = computed(() => ARMORY_PAGES
  .filter((page) => page.to !== "/overview" && [page.permission].flat().some(auth.hasPermission))
  .map((page) => ({ ...page, text: descriptions[page.to] ?? "", live: detail(page.to) })));

onMounted(async () => {
  const manage = auth.hasPermission("capabilities.manage");
  const [caps, tags, env, lim, mail] = await Promise.allSettled([
    manage ? capabilitiesAdminClient.list() : Promise.reject(new Error("skip")),
    auth.hasPermission("tickets.manage") ? ticketSettingsClient.get() : Promise.reject(new Error("skip")),
    manage ? environmentClient.get() : Promise.reject(new Error("skip")),
    manage ? limitsClient.get() : Promise.reject(new Error("skip")),
    manage ? emailSettingsClient.get() : Promise.reject(new Error("skip")),
  ]);
  const problems: string[] = [];
  const note = (r: PromiseRejectedResult) => { if ((r.reason as Error).message !== "skip") problems.push(errorMessage(r.reason)); };
  if (caps.status === "fulfilled") { counts.capabilities = caps.value.length; counts.online = caps.value.filter((c) => c.enabled).length; notices.report(true); }
  else { note(caps); if (manage) notices.report(false); }
  if (tags.status === "fulfilled") counts.tickets = Object.keys(tags.value.tags).length; else note(tags);
  if (env.status === "fulfilled") counts.settings = env.value.settings.filter((s) => s.stored).length; else note(env);
  if (lim.status === "fulfilled") counts.limits = [lim.value.pdf_merger, lim.value.media_downloader].filter((l) => l?.stored).length; else note(lim);
  if (mail.status === "fulfilled") counts.email = mail.value.to?.length ?? 0; else note(mail);
  error.value = problems[0] ?? "";
});
</script>

<template>
  <PageLayout class="admin-overview admin-panel" title="Workspace overview" wide>
    <p v-if="error" class="error" role="alert">Couldn't load all of the overview: {{ error }}</p>
    <div class="stats">
      <RouterLink v-for="tile in tiles" :key="tile.path" :to="tile.path" class="stat">
        <StatTile :label="tile.label" :value="counts[tile.key]" :unavailable="failed(tile.key)"><svg viewBox="0 0 24 24"><path :d="tile.icon" /></svg></StatTile>
        <span class="stat-link">{{ tile.link }}</span>
      </RouterLink>
    </div>
    <div v-if="notices.reachable === false" class="attention" role="status">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 9v5m0 3v.01" /></svg>
      <div class="attention-text"><strong>Armory does not answer</strong><span>Check that it is running. Counts may be missing until it does.</span></div>
      <RouterLink class="attention-action" to="/capabilities">Review</RouterLink>
    </div>
    <section class="admin-panel-card" aria-labelledby="overview-pages">
      <header class="admin-panel-head">
        <h2 id="overview-pages">Armory Admin</h2>
        <div class="admin-panel-tools"><PanelHelp title="Armory Admin"><p>Live counts for what Armory holds, and shortcuts to the pages that manage them. A dash means the count is still loading; Unavailable means it could not be loaded.</p></PanelHelp></div>
      </header>
      <div class="destinations">
        <RouterLink v-for="section in destinations" :key="section.to" :to="section.to" class="destination">
          <span class="destination-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path v-for="d in section.icon" :key="d" :d="d" /></svg></span>
          <div><h3>{{ section.label }}</h3><p>{{ section.text }}</p><small v-if="section.live" class="live">{{ section.live }}</small></div>
          <svg class="arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
        </RouterLink>
      </div>
    </section>
  </PageLayout>
</template>

<style scoped>
.error { margin: 0 0 12px; color: var(--danger); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 14px; }
.stat { display: grid; gap: 0; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); color: var(--text); text-decoration: none; }
.stat:hover { border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); }
.stat:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.stat :deep(.tile) { padding: 14px 16px 10px; border: 0; border-radius: 0; background: transparent; }
.stat :deep(.icon svg) { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.stat-link { padding: 8px 16px; border-top: 1px solid var(--border); background: var(--surface); color: var(--accent); font-size: 0.78em; }
.attention { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; padding: 12px 14px; border: 1px solid color-mix(in srgb, var(--warning) 40%, var(--border)); border-radius: var(--radius-lg); background: color-mix(in srgb, var(--warning) 6%, var(--bg)); }
.attention > svg { width: 22px; height: 22px; flex: none; fill: none; stroke: var(--warning); stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.attention-text { display: grid; flex: 1; min-width: 0; gap: 2px; font-size: 0.9em; }
.attention-text span { color: var(--muted); font-size: 0.9em; }
.attention-action { flex: none; display: inline-flex; align-items: center; min-height: 36px; padding: 5px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); font-size: 0.84rem; text-decoration: none; }
.attention-action:hover { background: var(--surface); }
.destinations { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.destination { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-bottom: 1px solid var(--border); color: var(--text); text-decoration: none; }
.destination:hover { background: var(--surface); }
.destination:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.destination-icon { display: grid; flex: none; place-items: center; width: 40px; height: 40px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--accent); background: var(--surface); }
.destination svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.destination h3 { margin: 0; font-size: 0.95em; }
.destination p { margin: 3px 0 0; color: var(--muted); font-size: 0.86em; }
.live { display: inline-block; margin-top: 6px; padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); color: var(--text); font: 650 0.74rem/1.5 var(--mono); }
.arrow { width: 16px; height: 16px; margin-inline-start: auto; color: var(--muted); }
@media (max-width: 767px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .destinations { grid-template-columns: 1fr; } .destination { padding: 12px; } .attention { flex-wrap: wrap; } .attention-action { min-height: 44px; } }
</style>
