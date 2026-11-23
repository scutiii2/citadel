<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { adminClient, type AdminSummary } from "../api/AdminClient";
import { ADMIN_NAV_PAGES, CONFIG_ISSUES_ICON } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import { errorMessage } from "../utils/errors";
import StatTile from "../components/admin/StatTile.vue";
import "../components/admin/admin.css";
import "../components/admin/adminPages.css";

const auth = useAuthStore();
const configIssues = useConfigIssuesStore();
const summary = ref<AdminSummary | null>(null);
const error = ref("");
const allowed = (permission: string | string[]) => (Array.isArray(permission) ? permission.some(auth.hasPermission) : auth.hasPermission(permission));
const canSummarize = computed(() => auth.hasPermission("accounts.view") || auth.hasPermission("invites.manage"));
/** A count the server could not give (or a failed request) is "unavailable", never zero. */
const unavailable = (key: keyof AdminSummary) => canSummarize.value && (!!error.value || (summary.value !== null && summary.value[key] === null));
const count = (key: keyof AdminSummary): number | null => summary.value?.[key] ?? null;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const descriptions: Record<string, string> = {
  "/admin/accounts": "Manage profiles, account status, and assigned roles.",
  "/admin/roles": "Define exactly what each role can view and change.",
  "/admin/invites": "Invite a member, check expiry, or revoke access.",
  "/admin/settings": "Control approval requirements for every account.",
};
/** What each destination shows beyond its description, when the live count is known. */
function detail(path: string): string {
  const s = summary.value;
  if (path === "/admin/accounts" && s?.accounts != null) return `${plural(s.accounts, "account")}${s.unverified ? ` · ${s.unverified} unverified` : ""}${s.disabled ? ` · ${s.disabled} disabled` : ""}`;
  if (path === "/admin/roles" && s?.roles != null) return plural(s.roles, "role");
  if (path === "/admin/invites" && s?.open_invites != null) return plural(s.open_invites, "open invite");
  return descriptions[path] ?? "";
}

const destinations = computed(() => [
  ...ADMIN_NAV_PAGES.filter((page) => page.to !== "/overview" && allowed(page.permission)).map((page) => ({ to: page.to, label: page.label, icon: page.icon, text: descriptions[page.to] ?? "", live: detail(page.to) })),
  ...(auth.hasPermission("config.issues.view") && configIssues.active.length
    ? [{ to: "/config-issues", label: "Config issues", icon: CONFIG_ISSUES_ICON, text: "Review problems in the configuration files.", live: `${plural(configIssues.errorCount, "error")} · ${plural(configIssues.warningCount, "warning")}` }]
    : []),
]);

onMounted(async () => {
  if (!canSummarize.value) return;
  try { summary.value = await adminClient.summary(); }
  catch (err) { error.value = errorMessage(err); }
});
</script>

<template>
  <PageLayout class="admin-overview admin-panel" title="Workspace overview" wide>
    <p v-if="error" class="error" role="alert">Couldn't load the overview: {{ error }}</p>
    <div v-if="canSummarize" class="stats">
      <RouterLink v-if="auth.hasPermission('accounts.view')" to="/admin/accounts" class="stat">
        <StatTile label="Accounts" :value="count('accounts')" :unavailable="unavailable('accounts')"><svg viewBox="0 0 24 24"><path d="M16 19v-1a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v1M10 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M20 19v-1a4 4 0 0 0-3-3.9M16 5.1a3 3 0 0 1 0 5.8" /></svg></StatTile>
        <span class="stat-link">Browse accounts</span>
      </RouterLink>
      <RouterLink v-if="auth.hasPermission('accounts.view')" to="/admin/accounts?status=unverified" class="stat">
        <StatTile label="Unverified" :value="count('unverified')" :unavailable="unavailable('unverified')" warn><svg viewBox="0 0 24 24"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6zM12 9v4m0 3h.01" /></svg></StatTile>
        <span class="stat-link">Review accounts</span>
      </RouterLink>
      <RouterLink v-if="auth.hasPermission('accounts.view')" to="/admin/accounts?status=disabled" class="stat">
        <StatTile label="Disabled" :value="count('disabled')" :unavailable="unavailable('disabled')"><svg viewBox="0 0 24 24"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M5.6 5.6l12.8 12.8" /></svg></StatTile>
        <span class="stat-link">Review accounts</span>
      </RouterLink>
      <RouterLink v-if="auth.hasPermission('invites.manage')" to="/admin/invites" class="stat">
        <StatTile label="Open invites" :value="count('open_invites')" :unavailable="unavailable('open_invites')"><svg viewBox="0 0 24 24"><path d="M3 6h18v12H3zM3 7l9 6 9-6" /></svg></StatTile>
        <span class="stat-link">Manage invites</span>
      </RouterLink>
    </div>
    <div v-if="auth.hasPermission('accounts.view') && summary?.unverified" class="attention" role="status">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 9v5m0 3v.01" /></svg>
      <div class="attention-text"><strong>{{ summary.unverified }} {{ summary.unverified === 1 ? 'account hasn’t' : 'accounts haven’t' }} verified their email</strong><span>Review their details or resend a verification email.</span></div>
      <RouterLink class="attention-action" to="/admin/accounts?status=unverified">Review</RouterLink>
    </div>
    <section class="admin-panel-card" aria-labelledby="overview-access">
      <header class="admin-panel-head"><h2 id="overview-access">Workspace access</h2><div class="admin-panel-tools"><RouterLink v-if="auth.hasPermission('invites.manage')" class="admin-icon accent" to="/admin/invites?create=1" aria-label="Invite member" title="Invite member"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19 8v6M16 11h6" /></svg></RouterLink><PanelHelp title="Workspace access">Live counts of the work waiting for you, and shortcuts to the pages that handle it. A dash means the count could not be loaded.</PanelHelp></div></header>
      <div class="destinations">
        <RouterLink v-for="section in destinations" :key="section.to" :to="section.to" class="destination">
          <span class="destination-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path v-for="d in section.icon" :key="d" :d="d" /></svg></span>
          <div><h3>{{ section.label }}</h3><p>{{ section.text }}</p><small v-if="section.live !== section.text" class="live">{{ section.live }}</small></div>
          <svg class="arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
        </RouterLink>
      </div>
    </section>
  </PageLayout>
</template>

<style scoped>
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
