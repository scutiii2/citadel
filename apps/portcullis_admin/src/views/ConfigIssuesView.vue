<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import type { ConfigIssue, ConfigIssueSeverity } from "../api/ConfigIssuesClient";
import AdminSearch from "../components/admin/AdminSearch.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import StatusFilters from "../components/admin/StatusFilters.vue";
import "../components/admin/admin.css";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import { adminAppUrl } from "../utils/siblings";

/** Problems in portcullis's config and secret files. File and key names only, never secret values.
 * The page opens only while there are issues; a check that succeeds and finds none leaves for the home
 * page, while a failed check keeps the page and its error. */
const store = useConfigIssuesStore();
const auth = useAuthStore();
const router = useRouter();
type Filter = "all" | ConfigIssueSeverity | "ignored";
const filter = ref<Filter>("all");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

const options = computed(() => [
  { id: "all", label: "All", count: store.active.length, tone: "accent" },
  { id: "error", label: "Errors", count: store.errorCount, tone: "danger", disabled: !store.errorCount },
  { id: "warning", label: "Warnings", count: store.warningCount, tone: "warning", disabled: !store.warningCount },
  { id: "ignored", label: "Ignored", count: store.ignored.length, tone: "muted", disabled: !store.ignored.length },
] as const);

/** Where an issue can be fixed from the admin apps, when its file is one they edit. */
interface Fix { label: string; to?: string; href?: string }
function fixFor(issue: ConfigIssue): Fix | null {
  if (issue.file === "config_app.json" && auth.hasPermission("settings.manage")) return { label: "Fix in Workspace settings", to: "/admin/settings" };
  if (issue.file === "Stronghold Tool services") return { label: "Fix in Stronghold Admin", href: adminAppUrl(26504) };
  return null;
}

const shown = computed(() => {
  const query = search.value.trim().toLowerCase();
  const pool = filter.value === "ignored" ? store.ignored : store.active;
  return pool.filter((i) => (filter.value === "all" || filter.value === "ignored" || i.severity === filter.value)
    && [i.file, i.key, i.message, i.severity].some((text) => text.toLowerCase().includes(query)));
});

/** One group per file, the files with errors first. */
const byFile = computed(() => {
  const groups = new Map<string, ConfigIssue[]>();
  for (const issue of shown.value) {
    const list = groups.get(issue.file) ?? [];
    list.push(issue);
    groups.set(issue.file, list);
  }
  const rank = (list: ConfigIssue[]) => (list.some((i) => i.severity === "error") ? 0 : 1);
  return [...groups.entries()]
    .map(([file, items]) => ({ file, items: [...items].sort((a, b) => Number(a.severity === "warning") - Number(b.severity === "warning")) }))
    .sort((a, b) => rank(a.items) - rank(b.items));
});

function restore(i: ConfigIssue): void {
  store.restore(i);
  if (!store.ignored.length) filter.value = "all";
}

async function check(): Promise<void> {
  await store.refresh();
  if (!store.error && store.issues.length === 0) await router.replace("/");
}
</script>

<template>
  <PageLayout class="config-issues" title="Config issues" wide>
    <p v-if="store.error" class="error" role="alert" data-test="check-error">The check failed: {{ store.error }}</p>
    <StatusFilters v-model="filter" label="Filter by level" :options="options" />
    <section class="admin-panel-card" aria-labelledby="issues-title">
      <header class="admin-panel-head">
        <h2 id="issues-title">Check results</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Check results"><p>Problems found in the Portcullis config and secret files, grouped by file. Use the refresh icon to check again; errors need fixing, warnings are advice.</p><p>The arrow opens the page where an issue can be fixed. The eye icon ignores a warning on this browser: it leaves the counts and alerts, and stays under Ignored until you restore it. Errors cannot be ignored.</p><p>Problems in <code>portcullis/configs</code> and <code>portcullis/secrets</code>. Secret files are re-read on every check; changes to <code>config_app.json</code> take effect once portcullis restarts.</p></PanelHelp>
          <button type="button" class="admin-icon" data-test="check" aria-label="Check again" title="Check again" :disabled="store.loading" @click="check"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" /></svg></button>
          <AdminSearch ref="searchField" v-model="search" label="Search issues" />
        </div>
      </header>
      <p v-if="store.loading && !store.issues.length" class="admin-panel-text muted" role="status">Checking…</p>
      <p v-else-if="!store.issues.length" class="admin-panel-text muted">{{ store.error ? "No results from the last check." : "No config issues found." }}</p>
      <p v-else-if="!store.active.length && filter !== 'ignored'" class="admin-panel-text muted">No active issues. {{ store.ignored.length }} ignored warning{{ store.ignored.length === 1 ? "" : "s" }}: open Ignored to review them.</p>
      <p v-else-if="!shown.length" class="admin-panel-text muted">No issues match these filters. <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <template v-else>
        <section v-for="g in byFile" :key="g.file" class="file" :aria-label="g.file">
          <div class="file-head"><code>{{ g.file }}</code><span class="muted">{{ plural(g.items.length, "problem") }}</span></div>
          <div v-for="(i, n) in g.items" :key="n" class="row">
            <span class="level" :class="i.severity"><span aria-hidden="true">{{ i.severity === "error" ? "✕" : "!" }}</span> {{ i.severity }}</span>
            <code class="key">{{ i.key }}</code>
            <span class="message">{{ i.message }}</span>
            <span class="row-actions">
              <template v-if="fixFor(i)">
                <RouterLink v-if="fixFor(i)!.to" class="admin-icon" :to="fixFor(i)!.to!" :aria-label="`${fixFor(i)!.label}: ${i.key}`" :title="fixFor(i)!.label" data-test="fix"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg></RouterLink>
                <a v-else class="admin-icon" :href="fixFor(i)!.href" :aria-label="`${fixFor(i)!.label}: ${i.key}`" :title="fixFor(i)!.label" data-test="fix"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg></a>
              </template>
              <button v-if="filter === 'ignored'" type="button" class="admin-icon" :aria-label="`Stop ignoring ${i.key}`" title="Stop ignoring" data-test="restore" @click="restore(i)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12s4-6 9-6 9 6 9 6-4 6-9 6-9-6-9-6M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6" /></svg></button>
              <button v-else-if="i.severity === 'warning'" type="button" class="admin-icon" :aria-label="`Ignore warning ${i.key}`" title="Ignore this warning" data-test="ignore" @click="store.ignore(i)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 6.2A9 9 0 0 1 12 6c5 0 9 6 9 6a15 15 0 0 1-2.9 3.5M6.6 6.6A15 15 0 0 0 3 12s4 6 9 6a8.6 8.6 0 0 0 3.4-.7M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg></button>
            </span>
          </div>
        </section>
      </template>
    </section>
  </PageLayout>
</template>

<style scoped>
.file + .file { border-top: 1px solid var(--border); }
.file-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 14px; background: var(--surface); font-size: 0.85em; }
.row { display: flex; align-items: baseline; gap: 10px; padding: 9px 14px; border-top: 1px solid var(--border); font-size: 0.9em; }
.level { flex-shrink: 0; min-width: 72px; padding: 1px 8px; border-radius: var(--radius-full); font-size: 0.78em; text-align: center; color: var(--tone); background: color-mix(in srgb, var(--tone) 12%, var(--bg)); }
.level.error { --tone: var(--status-failed); }
.level.warning { --tone: var(--warning); }
.key { flex-shrink: 0; padding: 1px 6px; border-radius: var(--radius-sm); background: var(--code-bg); }
.message { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; }
.row-actions { display: flex; flex: none; gap: 2px; margin-inline-start: auto; align-self: center; }
@media (max-width: 600px) { .row { flex-wrap: wrap; } }
</style>
