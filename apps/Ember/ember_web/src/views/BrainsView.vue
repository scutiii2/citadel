<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import PageLayout from "../components/PageLayout.vue";
import BrainConnectionForm from "../components/BrainConnectionForm.vue";
import MarkdownContent from "../components/MarkdownContent.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import BaseModal from "../components/BaseModal.vue";
import { brainsClient, type BrainResult, type BrainScope } from "../api/BrainsClient";
import { errorMessage } from "../utils/errors";
const route = useRoute();
type Scope = BrainScope | "both";
type Operation = "list" | "read" | "search" | "status";
type SearchHit = NonNullable<BrainResult["hits"]>[number];
const scope = ref<Scope>(route.query.scope === "personal" ? "personal" : route.query.scope === "both" ? "both" : "instance");
const path = ref(typeof route.query.path === "string" ? route.query.path : "");
const query = ref("");
const entries = ref<NonNullable<BrainResult["entries"]>>([]);
const folderPath = ref("");
const listingAvailable = ref(false);
const document = ref<{ scope: BrainScope; path: string; content: string } | null>(null);
const hits = ref<SearchHit[]>([]);
const feedback = ref<BrainResult | null>(null);
const connectionStatus = ref<BrainResult | null>(null);
const mode = ref<"browse" | "search">(scope.value === "both" ? "search" : "browse");
const searched = ref(false);
const mobileReading = ref(false);
const connectionOpen = ref(false);
const busy = ref(false);
const operation = ref<Operation | null>(null);
const error = ref("");
let lastRequest: { operation: Operation; path: string; scope: Scope } | null = null;
const scopeOptions = computed(() => [
  { value: "instance" as const, label: "Instance", disabled: busy.value },
  { value: "personal" as const, label: "Personal", disabled: busy.value },
  { value: "both" as const, label: "Both brains", disabled: busy.value },
]);
const breadcrumbs = computed(() => {
  const parts = folderPath.value.split("/").filter(Boolean);
  return [{ label: "Vault", path: "" }, ...parts.map((label, index) => ({ label, path: parts.slice(0, index + 1).join("/") }))];
});
function scopeLabel(value: Scope): string { return value === "both" ? "Both brains" : value === "personal" ? "Personal Brain" : "Instance Brain"; }
function fileName(value: string): string { return value.split("/").filter(Boolean).at(-1) ?? value; }
function parentPath(value: string): string { return value.split("/").slice(0, -1).join("/"); }

async function run(action: Operation, nextPath = path.value, targetScope = scope.value): Promise<void> {
  if (busy.value) return;
  if (targetScope === "both" && action !== "search") return;
  busy.value = true; error.value = ""; feedback.value = null; operation.value = action;
  lastRequest = { operation: action, path: nextPath, scope: targetScope };
  if (action === "search") { mode.value = "search"; searched.value = true; hits.value = []; mobileReading.value = false; }
  try {
    const result = await brainsClient.browse(targetScope, action, nextPath, query.value);
    feedback.value = result;
    if (result.status !== undefined || result.index_status !== undefined) connectionStatus.value = result;
    if (action === "list") {
      entries.value = result.entries ?? [];
      listingAvailable.value = result.entries !== undefined;
      folderPath.value = path.value = nextPath;
      mode.value = "browse"; mobileReading.value = false;
    } else if (action === "read" && result.content !== undefined && targetScope !== "both") {
      document.value = { scope: targetScope, path: nextPath, content: result.content };
      path.value = nextPath;
      mode.value = "browse"; mobileReading.value = true;
    } else if (action === "search") hits.value = result.hits ?? [];
  }
  catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; operation.value = null; }
}
function resetScope(nextScope: Scope): void {
  scope.value = nextScope;
  document.value = null; entries.value = []; hits.value = []; feedback.value = null; connectionStatus.value = null;
  path.value = folderPath.value = ""; error.value = ""; listingAvailable.value = false; mobileReading.value = false; searched.value = false;
  mode.value = nextScope === "both" ? "search" : "browse";
}
function selectScope(nextScope: Scope): void {
  if (busy.value || nextScope === scope.value) return;
  resetScope(nextScope);
  if (nextScope !== "both") void run("list", "");
}
async function openHit(hit: SearchHit): Promise<void> {
  if (busy.value) return;
  if (scope.value !== hit.scope) resetScope(hit.scope);
  await run("list", parentPath(hit.path), hit.scope);
  await run("read", hit.path, hit.scope);
}
function retry(): void { if (lastRequest) void run(lastRequest.operation, lastRequest.path, lastRequest.scope); }
onMounted(async () => {
  if (scope.value === "both") return;
  const target = path.value;
  await run("list", target ? parentPath(target) : "");
  if (target) await run("read", target);
});
</script>
<template>
  <PageLayout class="brains" :class="{ 'mobile-reading': mobileReading && mode === 'browse' }" title="Brains" description="Durable knowledge, shared and personal." wide fill>
    <template #actions>
      <button type="button" class="connection-button" @click="connectionOpen = true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="3" /><circle cx="15" cy="17" r="3" /></svg>
        <span>Personal connection</span>
      </button>
    </template>
    <template #toolbar>
      <div class="brain-toolbar">
        <div class="scope-line">
          <SegmentedControl :model-value="scope" :options="scopeOptions" aria-label="Brain scope" @update:model-value="selectScope" />
          <span class="connection-status" role="status">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7v.2" /></svg>
            <template v-if="connectionStatus">Connection: {{ connectionStatus.status?.replaceAll('_', ' ') ?? 'unknown' }} · Index: {{ connectionStatus.index_status?.replaceAll('_', ' ') ?? 'not checked' }}</template>
            <template v-else>{{ scope === 'both' ? 'Search across shared and personal knowledge' : 'Connection not checked' }}</template>
          </span>
        </div>
        <form class="search-form" role="search" @submit.prevent="run('search', '')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
          <input v-model="query" type="search" :maxlength="2000" aria-label="Search brains" :placeholder="scope === 'both' ? 'Search across both brains…' : `Search the ${scopeLabel(scope)}…`" :disabled="busy" />
          <button type="submit" :disabled="busy || !query.trim()" :aria-busy="busy && operation === 'search'">{{ busy && operation === 'search' ? 'Searching…' : 'Search' }}</button>
        </form>
      </div>
    </template>

    <div v-if="error || feedback?.message || feedback?.refreshing || feedback?.failures?.length" class="feedback">
      <div v-if="error" class="error" role="alert"><span>{{ error }}</span><button type="button" :disabled="busy" @click="retry">Try again</button></div>
      <p v-if="feedback?.message" role="status">{{ feedback.message }}</p>
      <p v-if="feedback?.refreshing" role="status">Indexing is in progress. Results use completed documents.</p>
      <p v-for="failure in feedback?.failures" :key="failure.scope" role="status">{{ scopeLabel(failure.scope as Scope) }}: {{ failure.message }}</p>
    </div>

    <section v-if="mode === 'search'" class="search-results" aria-label="Brain search results" :aria-busy="busy">
      <div class="results-head">
        <p>{{ busy ? 'Searching…' : searched ? `${hits.length} results` : 'Search both brains' }}</p>
        <button v-if="scope !== 'both'" type="button" :disabled="busy" @click="mode = 'browse'">Back to browsing</button>
      </div>
      <p v-if="!searched" class="empty-message">Find documents across your Personal Brain and the shared Instance Brain.</p>
      <p v-else-if="!busy && !error && hits.length === 0" class="empty-message">No documents match your search. Try a different word.</p>
      <article v-for="hit in hits" :key="`${hit.scope}:${hit.path}:${hit.heading}`" class="search-hit">
        <span class="scope-badge">{{ scopeLabel(hit.scope) }} · {{ hit.scope === 'personal' ? 'Only you' : 'Shared' }}</span>
        <h3><button type="button" :disabled="busy" @click="openHit(hit)">{{ hit.heading || fileName(hit.path) }}</button></h3>
        <p class="hit-path">{{ hit.connection_label }} · {{ hit.path }} · {{ hit.refresh_status.replaceAll('_', ' ') }}</p>
        <MarkdownContent :text="hit.content" />
      </article>
    </section>

    <div v-else class="brain-workspace" :class="{ reading: mobileReading }" :aria-busy="busy">
      <aside class="browser" aria-label="Brain folders and documents">
        <nav class="breadcrumbs" aria-label="Vault folders">
          <template v-for="(crumb, index) in breadcrumbs" :key="crumb.path">
            <span v-if="index" aria-hidden="true">/</span>
            <button type="button" :disabled="busy" :aria-current="index === breadcrumbs.length - 1 ? 'location' : undefined" @click="run('list', crumb.path)">{{ crumb.label }}</button>
          </template>
        </nav>
        <p v-if="busy && operation === 'list'" class="empty-message" role="status">Loading folder…</p>
        <ul v-else-if="entries.length" class="file-list" aria-label="Brain documents">
          <li v-for="entry in entries" :key="entry.path">
            <button type="button" class="file-row" :class="{ active: entry.path === document?.path }" :aria-current="entry.path === document?.path ? 'true' : undefined" :disabled="busy" :aria-label="entry.path" @click="run(entry.kind === 'folder' ? 'list' : 'read', entry.path)">
              <svg v-if="entry.kind === 'folder'" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h6l2 3h10v12H3z" /></svg>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>
              <span><strong>{{ fileName(entry.path) }}</strong><small>{{ entry.kind === 'folder' ? 'Folder' : 'Document' }}</small></span>
            </button>
          </li>
        </ul>
        <p v-else class="empty-message">{{ listingAvailable ? 'This folder is empty.' : 'Choose a folder or check the connection.' }}</p>
        <details class="open-path">
          <summary>Open a specific path</summary>
          <label>Vault-relative path<input v-model="path" maxlength="500" placeholder="Inbox/Example.md" :disabled="busy" /></label>
          <div class="path-actions"><button type="button" :disabled="busy" @click="run('list')">Browse folder</button><button type="button" :disabled="busy || !path.trim()" @click="run('read')">Read document</button></div>
        </details>
        <div class="browser-footer">
          <p>{{ scopeLabel(scope) }}<br>{{ scope === 'personal' ? 'Available only to your account.' : 'Readable by all signed-in users.' }}</p>
          <button type="button" :disabled="busy" :aria-busy="busy && operation === 'status'" @click="run('status', '')">{{ busy && operation === 'status' ? 'Checking…' : 'Check connection' }}</button>
        </div>
      </aside>
      <section class="reader" aria-label="Brain document reader">
        <header class="reader-head">
          <button type="button" class="back" :disabled="busy" @click="mobileReading = false">‹ All documents</button>
          <span class="reader-path">{{ document?.path || 'Document reader' }}</span>
          <span v-if="document" class="reader-audience">{{ document.scope === 'personal' ? 'Only you' : 'Shared' }}</span>
        </header>
        <div v-if="document" class="document-content" tabindex="0" aria-label="Document content">
          <p class="document-scope">{{ scopeLabel(document.scope) }}</p>
          <p v-if="busy && operation === 'read'" role="status">Opening document…</p>
          <MarkdownContent v-if="document.content" :text="document.content" />
          <p v-else class="empty-message">This document is empty.</p>
        </div>
        <div v-else class="reader-placeholder">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5c3-1 6-1 9 1 3-2 6-2 9-1v15c-3-1-6-1-9 1-3-2-6-2-9-1zM12 6v15" /></svg>
          <h3>{{ busy && operation === 'read' ? 'Opening document…' : 'Knowledge, within reach' }}</h3>
          <p>Choose a document to read, or search this brain.</p>
        </div>
        <footer v-if="document" class="reader-footer">Reading from the {{ scopeLabel(document.scope) }}</footer>
      </section>
    </div>

    <BaseModal class="connection-modal" :open="connectionOpen" title="Personal connection" @close="connectionOpen = false">
      <BrainConnectionForm scope="personal" />
    </BaseModal>
  </PageLayout>
</template>
<style scoped>
button { color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-full); padding: 7px 14px; font: inherit; font-size: .85em; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
button:hover:not(:disabled) { border-color: var(--accent); }
button:disabled { opacity: .5; cursor: default; }
button:focus-visible, input:focus-visible, summary:focus-visible, .document-content:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.connection-button { display: flex; align-items: center; gap: 8px; }
.connection-button svg { width: 16px; height: 16px; }
.connection-button circle { fill: var(--bg); }
.brain-toolbar { display: flex; flex-direction: column; gap: 16px; }
.scope-line { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.connection-status { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: .75em; overflow-wrap: anywhere; }
.connection-status svg { width: 14px; height: 14px; }
.search-form { display: flex; align-items: center; gap: 10px; padding: 7px 8px 7px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.search-form > svg { color: var(--muted); }
.search-form input { flex: 1; min-width: 0; width: 100%; border: 0; background: transparent; color: var(--text); font: inherit; font-size: .9em; }
.search-form button { flex-shrink: 0; }
.feedback { max-height: 25%; overflow: auto; padding: 0 0 12px; flex-shrink: 0; overflow-wrap: anywhere; font-size: .85em; }
.feedback p { margin: 4px 0; }
.feedback .error { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.feedback .error button { flex-shrink: 0; }
.brain-workspace { display: grid; grid-template-columns: 260px minmax(0, 1fr); flex: 1; min-height: 0; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.browser { display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow-y: auto; padding: 18px 12px; border-right: 1px solid var(--border); background: color-mix(in srgb, var(--surface) 50%, var(--bg)); }
.breadcrumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding: 0 10px 15px; font-size: .8em; color: var(--muted); }
.breadcrumbs button { min-width: 0; max-width: 100%; padding: 2px 0; border: 0; border-radius: var(--radius-sm); color: var(--muted); background: transparent; font-size: 1em; overflow-wrap: anywhere; }
.breadcrumbs button:hover { color: var(--accent); }
.file-list { padding: 0; margin: 0; list-style: none; }
.file-list li + li { margin-top: 4px; }
button.file-row { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 13px 10px; border-color: transparent; border-radius: var(--radius-md); background: transparent; text-align: left; }
.file-row > span { min-width: 0; }
.file-row svg { color: var(--muted); margin-top: 2px; }
.file-row strong { display: block; font-size: 1em; font-weight: 500; overflow-wrap: anywhere; }
.file-row small { display: block; margin-top: 5px; color: var(--muted); font-size: .8em; }
button.file-row:hover:not(:disabled) { background: var(--surface); }
button.file-row.active { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
.file-row.active svg { color: var(--accent); }
.open-path { margin: 20px 10px 0; padding-top: 12px; border-top: 1px solid var(--border); font-size: .8em; }
.open-path summary { cursor: pointer; color: var(--muted); }
.open-path label { display: grid; gap: 6px; margin-top: 12px; }
.open-path input { min-width: 0; width: 100%; padding: 8px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; }
.path-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.browser-footer { margin-top: auto; padding: 20px 10px 0; color: var(--muted); font-size: .75em; }
.browser-footer p { margin: 0 0 12px; line-height: 1.8; }
.browser-footer button { font-size: 1em; }
.reader { display: flex; flex-direction: column; min-height: 0; min-width: 0; background: var(--bg); }
.reader-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 26px; border-bottom: 1px solid var(--border); color: var(--muted); font-size: .75em; }
.reader-path { min-width: 0; overflow-wrap: anywhere; }
.reader-audience { flex-shrink: 0; }
.document-content { flex: 1; min-height: 0; overflow: auto; padding: 28px 32px; overflow-wrap: anywhere; line-height: 1.8; }
.document-content :deep(.markdown) { max-width: 780px; margin-inline: auto; }
.document-content :deep(h1) { font-size: 1.7em; font-weight: 600; line-height: 1.35; letter-spacing: -.025em; }
.document-content :deep(h2) { font-size: 1.25em; }
.document-content :deep(h3) { font-size: 1.05em; }
.document-scope { max-width: 780px; margin: 0 auto 16px; color: var(--accent); text-transform: uppercase; letter-spacing: .08em; font-size: .7em; }
.reader-footer { padding: 12px 26px; border-top: 1px solid var(--border); color: var(--muted); font-size: .75em; }
.reader-placeholder { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 28px; text-align: center; color: var(--muted); }
.reader-placeholder svg { width: 34px; height: 34px; color: var(--accent); }
.reader-placeholder h3 { margin: 0; font-size: 1.05em; color: var(--text); font-weight: 600; }
.reader-placeholder p { margin: 0; font-size: .9em; }
.empty-message { padding: 8px 10px; color: var(--muted); font-size: .9em; }
.back { display: none; }
.search-results { flex: 1; min-height: 0; overflow: auto; padding: 22px 28px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.results-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: var(--muted); font-size: .8em; }
.results-head p { margin: 0; }
.search-hit { padding: 24px 0; overflow-wrap: anywhere; }
.search-hit + .search-hit { border-top: 1px solid var(--border); }
.scope-badge { display: inline-block; padding: 2px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--muted); font-size: .75em; }
.search-hit h3 { margin: 10px 0; font-size: 1.05em; }
.search-hit h3 button { max-width: 100%; border: 0; border-radius: var(--radius-sm); padding: 0; text-align: left; font: inherit; color: var(--text); overflow-wrap: anywhere; }
.hit-path { margin: 0 0 14px; color: var(--muted); font-size: .75em; }
.search-hit :deep(.markdown) { font-size: .9em; }
.connection-modal :deep(.brain-connection) { margin: 0; padding: 0; border: 0; border-radius: 0; background: transparent; }
.connection-modal :deep(h3) { font-size: 1em; }
.connection-modal :deep(p) { overflow-wrap: anywhere; }
[aria-busy="true"]:is(.search-form button, .browser-footer button)::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 6px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); vertical-align: -1px; animation: brain-spin .7s linear infinite; }
@keyframes brain-spin { to { transform: rotate(360deg); } }
.error { color: var(--danger); }
@media (max-width: 900px) and (min-width: 768px) {
  .brain-workspace { grid-template-columns: 220px minmax(0, 1fr); }
  .document-content { padding: 24px; }
}
@media (max-width: 767px) {
  .brains :deep(.page-column) { padding: 20px 16px 12px; }
  .brains :deep(.page-head) { flex-direction: row; align-items: flex-start; gap: 12px; margin-bottom: 18px; }
  .connection-button { min-height: 44px; }
  .connection-button span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .scope-line :deep(.segmented-control), .scope-line :deep(.segmented) { width: 100%; }
  .scope-line :deep(button.segment) { flex: 1; min-height: 44px; padding-inline: 8px; }
  .connection-status { font-size: .7em; }
  .search-form input { font-size: max(1em, 16px); }
  .search-form button { min-height: 40px; padding-inline: 12px; }
  .brain-workspace { grid-template-columns: minmax(0, 1fr); }
  .browser { border-right: 0; padding: 16px 12px; }
  .brain-workspace:not(.reading) .reader, .brain-workspace.reading .browser { display: none; }
  .mobile-reading :deep(.page-toolbar) { display: none; }
  button.file-row { min-height: 76px; padding: 16px 10px; }
  .breadcrumbs button { min-height: 36px; }
  .reader-head { padding: 12px 16px; }
  .reader-head .reader-path { display: none; }
  .back { display: inline-block; padding: 6px 0; border: 0; min-height: 40px; color: var(--muted); font-size: 1.1em; }
  .document-content { padding: 22px 20px; }
  .reader-footer { padding: 12px 16px; }
  .search-results { padding: 18px 20px; }
  dialog.connection-modal { position: fixed; inset: auto 0 var(--rail-height); width: 100%; max-width: none; max-height: calc(100dvh - var(--rail-height) - env(safe-area-inset-top, 0px) - 16px); margin: 0; border-radius: var(--radius-xl) var(--radius-xl) 0 0; }
}
</style>
