<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, reactive, ref } from "vue";
import { RouterLink } from "vue-router";
import { brainSettingsClient } from "../api/BrainSettingsClient";
import { logsClient } from "../api/LogsClient";
import { ticketsAdminClient } from "../api/TicketsAdminClient";
import { toolServicesClient } from "../api/ToolServicesClient";
import { usageClient } from "../api/UsageClient";
import { usageSettingsClient } from "../api/UsageSettingsClient";
import { PanelHelp } from "@citadel/ui";
import { StatTile } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { LOG_PERMISSIONS, STRONGHOLD_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { useNoticesStore } from "../stores/notices";
import { errorMessage } from "../utils/errors";
import "@citadel/ui/admin.css";

/** The home page: live counts for what Stronghold holds, an alert while Stronghold does not answer, and shortcuts
 * to each page. A count that could not be loaded is "Unavailable", never zero. */
const auth = useAuthStore();
const notices = useNoticesStore();
const counts = reactive<Record<string, number | null>>({ usage: null, analytics: null, tickets: null, services: null, enabled: null, usageSettings: null, brainSettings: null });
const error = ref("");
const failed = (key: string) => !!error.value && counts[key] === null;
const may = (path: string) => STRONGHOLD_PAGES.some((page) => page.to === path && [page.permission].flat().some(auth.hasPermission));
const mayLogs = computed(() => LOG_PERMISSIONS.some(auth.hasPermission));

const tiles = computed(() => [
  { path: "/usage", key: "usage", label: "Accounts with usage", link: "Review usage", icon: "M3 3v16a2 2 0 0 0 2 2h16M18 17V9M13 17V5M8 17v-3", show: true },
  { path: "/analytics", key: "analytics", label: "Log entries, 7 days", link: "Open analytics", icon: "M22 12h-4l-3 9L9 3l-3 9H2", show: mayLogs.value },
  { path: "/tickets", key: "tickets", label: "Open tickets", link: "Open tickets", icon: "M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2ZM13 5v2M13 17v2M13 11v2", show: true },
  { path: "/tool-services", key: "enabled", label: "Enabled tool services", link: "Manage tool services", icon: "M4 7h16M4 12h16M4 17h16M8 5v4M16 10v4M10 15v4", show: true },
  { path: "/usage-settings", key: "usageSettings", label: "Changed usage settings", link: "Open usage settings", icon: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6", show: true },
  { path: "/brain-settings", key: "brainSettings", label: "Changed brain settings", link: "Open brain settings", icon: "M12 18V5M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4", show: true },
].filter((tile) => tile.show && may(tile.path)));

const descriptions: Record<string, string> = {
  "/usage": "Each account's token usage and limits.",
  "/analytics": "Activity, errors and network traffic.",
  "/tickets": "What needs attention in the work queue.",
  "/usage-settings": "Token limits and model prices.",
  "/brain-settings": "Memory and sharing limits.",
  "/tool-services": "The tool services Stronghold reaches.",
};
function detail(path: string): string {
  if (path === "/usage" && counts.usage !== null) return `${counts.usage} ${counts.usage === 1 ? "account" : "accounts"}`;
  if (path === "/analytics" && counts.analytics !== null) return `${counts.analytics} entries in 7 days`;
  if (path === "/tickets" && counts.tickets !== null) return `${counts.tickets} open`;
  if (path === "/tool-services" && counts.services !== null) return `${counts.enabled ?? 0} of ${counts.services} enabled`;
  if (path === "/usage-settings" && counts.usageSettings !== null) return `${counts.usageSettings} changed`;
  if (path === "/brain-settings" && counts.brainSettings !== null) return `${counts.brainSettings} changed`;
  return "";
}
const destinations = computed(() => STRONGHOLD_PAGES
  .filter((page) => page.to !== "/overview" && [page.permission].flat().some(auth.hasPermission))
  .map((page) => ({ ...page, text: descriptions[page.to] ?? "", live: detail(page.to) })));

const skip = () => Promise.reject(new Error("skip"));
onMounted(async () => {
  const [usage, logs, tickets, services, usageSettings, brain] = await Promise.allSettled([
    auth.hasPermission("usage.all.view") ? usageClient.allAccounts(7) : skip(),
    mayLogs.value ? logsClient.analytics("7d") : skip(),
    auth.hasPermission("tickets.manage") ? ticketsAdminClient.stats() : skip(),
    auth.hasPermission("tool_services.manage") ? toolServicesClient.list() : skip(),
    auth.hasPermission("settings.manage") ? usageSettingsClient.get() : skip(),
    auth.hasPermission("settings.manage") ? brainSettingsClient.get() : skip(),
  ]);
  const problems: string[] = [];
  const note = (r: PromiseRejectedResult) => { if ((r.reason as Error).message !== "skip") problems.push(errorMessage(r.reason)); };
  if (usage.status === "fulfilled") { counts.usage = usage.value.length; notices.report(true); } else { note(usage); if (auth.hasPermission("usage.all.view")) notices.report(false); }
  if (logs.status === "fulfilled") counts.analytics = Object.values(logs.value.totals).reduce((sum, total) => sum + (total?.current ?? 0), 0); else note(logs);
  if (tickets.status === "fulfilled") counts.tickets = tickets.value.open; else note(tickets);
  if (services.status === "fulfilled") { counts.services = services.value.length; counts.enabled = services.value.filter((s) => s.enabled).length; } else note(services);
  if (usageSettings.status === "fulfilled") counts.usageSettings = Object.values(usageSettings.value.stored).filter(Boolean).length; else note(usageSettings);
  if (brain.status === "fulfilled") counts.brainSettings = Object.values(brain.value.stored).filter(Boolean).length; else note(brain);
  error.value = problems[0] ?? "";
});
</script>

<template>
  <PageLayout class="admin-overview admin-panel" title="Workspace overview" wide>
    <ActionMessage v-if="error" kind="error" :text="`Couldn't load all of the overview: ${error}`" />
    <div class="stats">
      <RouterLink v-for="tile in tiles" :key="tile.path" :to="tile.path" class="stat">
        <StatTile :label="tile.label" :value="counts[tile.key]" :unavailable="failed(tile.key)"><svg viewBox="0 0 24 24"><path :d="tile.icon" /></svg></StatTile>
        <span class="stat-link">{{ tile.link }}</span>
      </RouterLink>
    </div>
    <div v-if="notices.reachable === false" class="attention" role="status">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 9v5m0 3v.01" /></svg>
      <div class="attention-text"><strong>Stronghold does not answer</strong><span>Check that it is running. Counts may be missing until it does.</span></div>
      <RouterLink class="attention-action" to="/overview">Review</RouterLink>
    </div>
    <section class="admin-panel-card" aria-labelledby="overview-pages">
      <header class="admin-panel-head">
        <h2 id="overview-pages">Stronghold Admin</h2>
        <div class="admin-panel-tools"><PanelHelp title="Stronghold Admin"><p>Live counts for what Stronghold holds, and shortcuts to the pages that manage them. A dash means the count is still loading; Unavailable means it could not be loaded.</p></PanelHelp></div>
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
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-bottom: 14px; }
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
