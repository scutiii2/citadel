<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import { PanelHelp } from "@citadel/ui";
import { StatTile } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { TREASURY_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { useNoticesStore } from "../stores/notices";
import { errorMessage } from "../utils/errors";
import "@citadel/ui/admin.css";

/** The home page: live counts for what Treasury serves and keeps, an alert while Treasury does not answer,
 * and shortcuts to each page. A count that could not be loaded is "Unavailable", never zero. */
const auth = useAuthStore();
const notices = useNoticesStore();
const instances = ref<number | null>(null);
const connections = ref<number | null>(null);
const services = ref<number | null>(null);
const outside = ref<number | null>(null);
const error = ref("");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const failed = (value: number | null) => !!error.value && value === null;

const descriptions: Record<string, string> = {
  "/instances": "The databases Treasury serves and the connections each may use.",
  "/connections": "The databases Treasury keeps data in, and the cache defaults.",
  "/services": "Where Citadel services can reach each other.",
  "/outside": "Outside services and the addresses they are reached at.",
};
function detail(path: string): string {
  if (path === "/instances" && instances.value !== null) return plural(instances.value, "instance");
  if (path === "/connections" && connections.value !== null) return plural(connections.value, "connection");
  if (path === "/services" && services.value !== null) return plural(services.value, "service");
  if (path === "/outside" && outside.value !== null) return plural(outside.value, "outside service");
  return "";
}
const destinations = computed(() => TREASURY_PAGES
  .filter((page) => page.to !== "/overview" && [page.permission].flat().some(auth.hasPermission))
  .map((page) => ({ ...page, text: descriptions[page.to] ?? "", live: detail(page.to) })));

onMounted(async () => {
  const [view, conns, svc, out] = await Promise.allSettled([
    treasuryAdminClient.get(), treasuryAdminClient.connections(), treasuryAdminClient.getServices(), treasuryAdminClient.getOutside(),
  ]);
  const problems: string[] = [];
  if (view.status === "fulfilled") { instances.value = view.value.instances.length; notices.report(view.value.reachable); }
  else problems.push(errorMessage(view.reason));
  if (conns.status === "fulfilled") connections.value = conns.value.connections.length;
  else problems.push(errorMessage(conns.reason));
  if (svc.status === "fulfilled") services.value = svc.value.services.length;
  else problems.push(errorMessage(svc.reason));
  if (out.status === "fulfilled") outside.value = out.value.groups.length;
  else problems.push(errorMessage(out.reason));
  error.value = problems[0] ?? "";
});
</script>

<template>
  <PageLayout class="admin-overview admin-panel" title="Workspace overview" wide>
    <ActionMessage v-if="error" kind="error" :text="`Couldn't load all of the overview: ${error}`" />
    <div class="stats">
      <RouterLink to="/instances" class="stat">
        <StatTile label="Instances" :value="instances" :unavailable="failed(instances)"><svg viewBox="0 0 24 24"><path d="M3 5a9 3 0 1 0 18 0 9 3 0 1 0-18 0M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3" /></svg></StatTile>
        <span class="stat-link">Browse instances</span>
      </RouterLink>
      <RouterLink to="/connections" class="stat">
        <StatTile label="Connections" :value="connections" :unavailable="failed(connections)"><svg viewBox="0 0 24 24"><path d="M9 17H7a5 5 0 0 1 0-10h2M15 7h2a5 5 0 0 1 0 10h-2M8 12h8" /></svg></StatTile>
        <span class="stat-link">Manage connections</span>
      </RouterLink>
      <RouterLink to="/services" class="stat">
        <StatTile label="Services" :value="services" :unavailable="failed(services)"><svg viewBox="0 0 24 24"><path d="M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01" /></svg></StatTile>
        <span class="stat-link">Browse services</span>
      </RouterLink>
      <RouterLink to="/outside" class="stat">
        <StatTile label="Outside services" :value="outside" :unavailable="failed(outside)"><svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3" /></svg></StatTile>
        <span class="stat-link">Browse outside services</span>
      </RouterLink>
    </div>
    <div v-if="notices.reachable === false" class="attention" role="status">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 9v5m0 3v.01" /></svg>
      <div class="attention-text"><strong>Treasury does not answer</strong><span>Check that it is running. Counts may be missing until it does.</span></div>
      <RouterLink class="attention-action" to="/instances">Review</RouterLink>
    </div>
    <section class="admin-panel-card" aria-labelledby="overview-pages">
      <header class="admin-panel-head">
        <h2 id="overview-pages">Treasury Admin</h2>
        <div class="admin-panel-tools"><PanelHelp title="Treasury Admin"><p>Live counts for what Treasury serves and keeps, and shortcuts to the pages that manage them. A dash means the count could not be loaded.</p></PanelHelp></div>
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
