<script setup lang="ts">
import ActionMessage from "../components/admin/ActionMessage.vue";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import PanelHelp from "../components/admin/PanelHelp.vue";
import StatTile from "../components/admin/StatTile.vue";
import PageLayout from "../components/PageLayout.vue";
import { canOpen, LEGION_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** The home page: live counts of agents and MCP servers, an alert for offline agents, and shortcuts to each page.
 * A count the server could not give is "unavailable", never zero. */
const auth = useAuthStore();
const canManage = computed(() => auth.hasPermission("agents.manage"));
const agents = ref<{ id: string; enabled?: boolean }[] | null>(null);
const live = ref<Record<string, { status: string }> | null>(null);
const servers = ref<number | null>(null);
const error = ref("");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const statusOf = (agent: { id: string; enabled?: boolean }): string => (agent.enabled === false ? "disabled" : live.value?.[agent.id]?.status ?? "unknown");
const counts = computed(() => {
  const total = agents.value?.length ?? null;
  const by = (status: string) => (agents.value && live.value ? agents.value.filter((a) => statusOf(a) === status).length : null);
  return { total, running: by("running"), offline: by("offline"), disabled: by("disabled") };
});
const unavailable = (value: number | null) => canManage.value && !!error.value && value === null;

const descriptions: Record<string, string> = {
  "/agents": "Create agents, set their models and tools, and see which are running.",
  "/connections": "Model gateways and the MCP servers agents can use.",
  "/tuning": "Response-limit ceilings that cap what any agent may ask for.",
};
function detail(path: string): string {
  if (path === "/agents" && counts.value.total !== null) return `${plural(counts.value.total, "agent")}${counts.value.offline ? ` · ${counts.value.offline} offline` : ""}`;
  if (path === "/connections" && servers.value !== null) return plural(servers.value, "MCP server");
  return "";
}
const destinations = computed(() => LEGION_PAGES
  .filter((page) => page.to !== "/overview" && canOpen(page.permission, auth.hasPermission))
  .map((page) => ({ ...page, text: descriptions[page.to] ?? "", live: detail(page.to) })));

onMounted(async () => {
  if (!canManage.value) return;
  const [files, statuses, mcp] = await Promise.allSettled([agentsAdminClient.list(), agentsAdminClient.live(), agentsAdminClient.servers()]);
  if (files.status === "fulfilled") agents.value = files.value;
  else error.value = errorMessage(files.reason);
  // Agent statuses come from the running agents; without them every agent is "unknown", not offline.
  if (statuses.status === "fulfilled") live.value = statuses.value;
  if (mcp.status === "fulfilled") servers.value = Object.keys(mcp.value).length;
  else if (!error.value) error.value = errorMessage(mcp.reason);
});
</script>

<template>
  <PageLayout class="admin-overview admin-panel" title="Workspace overview" wide>
    <ActionMessage v-if="error" kind="error" :text="`Couldn't load all of the overview: ${error}`" />
    <div v-if="canManage" class="stats">
      <RouterLink to="/agents" class="stat">
        <StatTile label="Agents" :value="counts.total" :unavailable="unavailable(counts.total)"><svg viewBox="0 0 24 24"><path d="M3 21v-3a5 5 0 0 1 5-5h3a5 5 0 0 1 5 5v3M20 21v-3a5 5 0 0 0-3-4M13.5 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0" /></svg></StatTile>
        <span class="stat-link">Browse agents</span>
      </RouterLink>
      <RouterLink to="/agents" class="stat">
        <StatTile label="Running" :value="counts.running" :unavailable="unavailable(counts.running)"><svg viewBox="0 0 24 24"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9 12l2 2 4-4" /></svg></StatTile>
        <span class="stat-link">Browse agents</span>
      </RouterLink>
      <RouterLink to="/agents?status=offline" class="stat">
        <StatTile label="Offline" :value="counts.offline" :unavailable="unavailable(counts.offline)" warn><svg viewBox="0 0 24 24"><path d="M12 8v5m0 3h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18" /></svg></StatTile>
        <span class="stat-link">Review agents</span>
      </RouterLink>
      <RouterLink to="/connections" class="stat">
        <StatTile label="MCP servers" :value="servers" :unavailable="unavailable(servers)"><svg viewBox="0 0 24 24"><path d="M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01" /></svg></StatTile>
        <span class="stat-link">Manage connections</span>
      </RouterLink>
    </div>
    <div v-if="canManage && counts.offline" class="attention" role="status">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 9v5m0 3v.01" /></svg>
      <div class="attention-text"><strong>{{ counts.offline }} {{ counts.offline === 1 ? 'agent is' : 'agents are' }} offline</strong><span>Open an agent to check its address, or enable and restart it.</span></div>
      <RouterLink class="attention-action" to="/agents?status=offline">Review</RouterLink>
    </div>
    <section class="admin-panel-card" aria-labelledby="overview-pages">
      <header class="admin-panel-head">
        <h2 id="overview-pages">Legion Admin</h2>
        <div class="admin-panel-tools"><PanelHelp title="Legion Admin"><p>Live counts for the agents and MCP servers Legion runs, and shortcuts to the pages that manage them. A dash means the count could not be loaded.</p></PanelHelp></div>
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
