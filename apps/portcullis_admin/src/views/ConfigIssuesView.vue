<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import type { ConfigIssue, ConfigIssueSeverity } from "../api/ConfigIssuesClient";
import AdminSearch from "../components/admin/AdminSearch.vue";
import StatusFilters from "../components/admin/StatusFilters.vue";
import "../components/admin/admin.css";
import { useConfigIssuesStore } from "../stores/configIssues";

/** Problems in portcullis's config and secret files. File and key names only, never secret values.
 * The page opens only while there are issues; a check that succeeds and finds none leaves for the home
 * page, while a failed check keeps the page and its error. */
const store = useConfigIssuesStore();
const router = useRouter();
type Filter = "all" | ConfigIssueSeverity;
const filter = ref<Filter>("all");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

const options = computed(() => [
  { id: "all", label: "All", count: store.issues.length, tone: "accent" },
  { id: "error", label: "Errors", count: store.errorCount, tone: "danger", disabled: !store.errorCount },
  { id: "warning", label: "Warnings", count: store.warningCount, tone: "warning", disabled: !store.warningCount },
] as const);

const shown = computed(() => {
  const query = search.value.trim().toLowerCase();
  return store.issues.filter((i) => (filter.value === "all" || i.severity === filter.value)
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

async function check(): Promise<void> {
  await store.refresh();
  if (!store.error && store.issues.length === 0) await router.replace("/");
}
</script>

<template>
  <PageLayout class="config-issues" title="Config issues" wide>
    <template #actions><button type="button" class="chip" data-test="check" :disabled="store.loading" @click="check">Check again</button></template>
    <p class="muted intro">
      Problems in <code>portcullis/configs</code> and <code>portcullis/secrets</code>. Secret files are re-read on
      every check; changes to <code>config_app.json</code> take effect once portcullis restarts.
    </p>
    <p v-if="store.error" class="error" role="alert" data-test="check-error">The check failed: {{ store.error }}</p>
    <StatusFilters v-model="filter" label="Filter by level" :options="options" />
    <section class="admin-panel-card" aria-labelledby="issues-title">
      <header class="admin-panel-head">
        <h2 id="issues-title">Check results</h2>
        <div class="admin-panel-tools"><AdminSearch ref="searchField" v-model="search" label="Search issues" /></div>
      </header>
      <p v-if="store.loading && !store.issues.length" class="admin-panel-text muted" role="status">Checking…</p>
      <p v-else-if="!store.issues.length" class="admin-panel-text muted">{{ store.error ? "No results from the last check." : "No config issues found." }}</p>
      <p v-else-if="!shown.length" class="admin-panel-text muted">No issues match these filters. <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <template v-else>
        <section v-for="g in byFile" :key="g.file" class="file" :aria-label="g.file">
          <div class="file-head"><code>{{ g.file }}</code><span class="muted">{{ plural(g.items.length, "problem") }}</span></div>
          <div v-for="(i, n) in g.items" :key="n" class="row">
            <span class="level" :class="i.severity"><span aria-hidden="true">{{ i.severity === "error" ? "✕" : "!" }}</span> {{ i.severity }}</span>
            <code class="key">{{ i.key }}</code>
            <span class="message">{{ i.message }}</span>
          </div>
        </section>
      </template>
    </section>
  </PageLayout>
</template>

<style scoped>
.intro { margin: 0 0 12px; }
.file + .file { border-top: 1px solid var(--border); }
.file-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 14px; background: var(--surface); font-size: 0.85em; }
.row { display: flex; align-items: baseline; gap: 10px; padding: 9px 14px; border-top: 1px solid var(--border); font-size: 0.9em; }
.level { flex-shrink: 0; min-width: 72px; padding: 1px 8px; border-radius: var(--radius-full); font-size: 0.78em; text-align: center; color: var(--tone); background: color-mix(in srgb, var(--tone) 12%, var(--bg)); }
.level.error { --tone: var(--status-failed); }
.level.warning { --tone: var(--warning); }
.key { flex-shrink: 0; padding: 1px 6px; border-radius: var(--radius-sm); background: var(--code-bg); }
.message { min-width: 0; overflow-wrap: anywhere; }
@media (max-width: 600px) { .row { flex-wrap: wrap; } }
</style>
