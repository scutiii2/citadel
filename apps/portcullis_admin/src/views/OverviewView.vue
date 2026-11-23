<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
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
  ...(auth.hasPermission("config.issues.view") && configIssues.issues.length
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
    <template #actions><RouterLink v-if="auth.hasPermission('invites.manage')" class="primary" to="/admin/invites?create=1">Invite member</RouterLink></template>

    <p v-if="error" class="error" role="alert">Couldn't load the overview: {{ error }}</p>
    <div v-if="canSummarize" class="stats">
      <RouterLink v-if="auth.hasPermission('accounts.view')" to="/admin/accounts"><StatTile label="Accounts" :value="count('accounts')" :unavailable="unavailable('accounts')" /><span class="stat-link">Browse accounts →</span></RouterLink>
      <RouterLink v-if="auth.hasPermission('accounts.view')" to="/admin/accounts?status=unverified"><StatTile label="Unverified" :value="count('unverified')" :unavailable="unavailable('unverified')" warn /><span class="stat-link">Review accounts →</span></RouterLink>
      <RouterLink v-if="auth.hasPermission('accounts.view')" to="/admin/accounts?status=disabled"><StatTile label="Disabled" :value="count('disabled')" :unavailable="unavailable('disabled')" /><span class="stat-link">Review accounts →</span></RouterLink>
      <RouterLink v-if="auth.hasPermission('invites.manage')" to="/admin/invites"><StatTile label="Open invites" :value="count('open_invites')" :unavailable="unavailable('open_invites')" /><span class="stat-link">Manage invites →</span></RouterLink>
    </div>
    <div v-if="auth.hasPermission('accounts.view') && summary?.unverified" class="admin-info">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 10 18H2zM12 9v5m0 3v1" /></svg>
      <div><h3>{{ summary.unverified }} {{ summary.unverified === 1 ? 'account hasn’t' : 'accounts haven’t' }} verified their email</h3><p>Review their details or resend a verification email.</p></div>
      <RouterLink class="small" to="/admin/accounts?status=unverified">Review accounts</RouterLink>
    </div>
    <section class="admin-panel-card" aria-labelledby="overview-access">
      <header class="admin-panel-head"><h2 id="overview-access">Workspace access</h2></header>
      <div class="destinations">
        <RouterLink v-for="section in destinations" :key="section.to" :to="section.to" class="destination">
          <span class="destination-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path v-for="d in section.icon" :key="d" :d="d" /></svg></span>
          <div><h3>{{ section.label }}</h3><p>{{ section.text }}</p><small v-if="section.live !== section.text" class="live">{{ section.live }}</small></div>
          <span class="arrow" aria-hidden="true">→</span>
        </RouterLink>
      </div>
    </section>
  </PageLayout>
</template>

<style scoped>
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 14px; }
.stats > a { position: relative; color: var(--text); text-decoration: none; border-radius: var(--radius-lg); }
.stats > a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.stats :deep(.tile) { padding: 16px 18px 42px; background: var(--bg); }
.stat-link { position: absolute; bottom: 15px; left: 18px; color: var(--accent); font-size: 0.78em; }
.admin-info { margin-bottom: 14px; }
.destinations { display: grid; }
.destination { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-bottom: 1px solid var(--border); color: var(--text); text-decoration: none; }
.destination:last-child { border-bottom: 0; }
.destination:hover { background: var(--surface); }
.destination:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.destination-icon { display: flex; flex-shrink: 0; padding: 10px; border-radius: var(--radius-md); color: var(--accent); background: var(--surface); }
.destination svg { width: 20px; height: 20px; }
.destination h3 { margin: 0; font-size: 0.95em; }
.destination p { margin: 4px 0 0; color: var(--muted); font-size: 0.86em; }
.live { display: block; margin-top: 4px; color: var(--text); font: 650 0.78rem/1.2 var(--mono); }
.arrow { margin-left: auto; color: var(--muted); }
@media (max-width: 767px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .destination { padding: 12px; } }
</style>
