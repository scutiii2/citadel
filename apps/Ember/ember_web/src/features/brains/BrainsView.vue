<script setup lang="ts">
import WorkspaceLayout from "../../components/layout/WorkspaceLayout.vue";
import { computed, nextTick, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import PageLayout from "../../components/layout/PageLayout.vue";
import BrainConnectionForm from "./components/BrainConnectionForm.vue";
import MarkdownContent from "../../components/content/MarkdownContent.vue";
import ListRow from "../../components/ui/lists/ListRow.vue";
import SearchField from "../../components/ui/lists/SearchField.vue";
import BackButton from "../../components/ui/buttons/BackButton.vue";
import SegmentedControl from "../../components/ui/forms/SegmentedControl.vue";
import BaseModal from "../../components/ui/dialogs/BaseModal.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { useNarrow } from "../../composables/useNarrow";
import "../../components/layout/infoPage.css";
import { brainsClient, type BrainResult, type BrainScope } from "./api/BrainsClient";
import { errorMessage } from "../../utils/errors";
const route = useRoute();
const narrow = useNarrow();
const readerContent = ref<HTMLElement | null>(null);
const documentList = ref<HTMLElement | null>(null);
const searchField = ref<InstanceType<typeof SearchField> | null>(null);
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
      await nextTick();
      readerContent.value?.focus();
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
function showBrowser(): void {
  mobileReading.value = false;
  void nextTick(() => {
    const row = Array.from(documentList.value?.querySelectorAll<HTMLButtonElement>("button[data-path]") ?? [])
      .find(button => button.dataset.path === document.value?.path);
    if (row) row.focus();
    else searchField.value?.$el.querySelector("input")?.focus();
  });
}
async function closeConnection(): Promise<void> {
  connectionOpen.value = false;
  // BaseModal closes its native dialog after a render tick; restore focus after it.
  await nextTick();
  await nextTick();
  if (!connectionOpen.value && narrow.value && mobileReading.value) readerContent.value?.focus();
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
  <PageLayout class="brains info-content" :class="{ 'mobile-reading': mobileReading }" title="Brains" description="Durable knowledge, shared and personal." wide fill>
    <div v-if="error || feedback?.message || feedback?.refreshing || feedback?.failures?.length" class="feedback">
      <StateMessage v-if="error" kind="error" @retry="retry">{{ error }}</StateMessage>
      <p v-if="feedback?.message" role="status">{{ feedback.message }}</p>
      <p v-if="feedback?.refreshing" role="status">Indexing is in progress. Results use completed documents.</p>
      <p v-for="failure in feedback?.failures" :key="failure.scope" role="status">{{ scopeLabel(failure.scope as Scope) }}: {{ failure.message }}</p>
    </div>
    <WorkspaceLayout class="brain-workspace" :class="{ reading: mobileReading }" :aria-busy="busy">
      <aside class="browser" aria-label="Brain folders and documents">
        <div class="list-heading"><span>Knowledge</span><span>{{ scope === 'both' ? 'Both brains' : scope === 'personal' ? 'Personal' : 'Instance' }}</span></div>
        <div class="scope-line"><SegmentedControl :model-value="scope" :options="scopeOptions" aria-label="Brain scope" @update:model-value="selectScope" /></div>
        <form class="search-form" role="search" @submit.prevent="run('search', '')">
          <SearchField ref="searchField" v-model="query" label="Search brains" :maxlength="2000" :placeholder="scope === 'both' ? 'Search across both brains…' : 'Search this brain…'" :disabled="busy">
            <button type="submit" class="link-btn" :disabled="busy || !query.trim()" :aria-busy="busy && operation === 'search'">{{ busy && operation === 'search' ? 'Searching…' : 'Search' }}</button>
          </SearchField>
        </form>
        <div class="browser-head">
          <div v-if="mode === 'search'" class="results-head">
            <span>{{ busy && operation === 'search' ? 'Searching…' : searched ? `${hits.length} results` : 'Search both brains' }}</span>
            <button v-if="scope !== 'both'" type="button" class="link-btn" :disabled="busy" @click="mode = 'browse'">Back to browsing</button>
          </div>
          <nav v-else class="breadcrumbs" aria-label="Vault folders">
            <template v-for="(crumb, index) in breadcrumbs" :key="crumb.path"><span v-if="index" aria-hidden="true">/</span><button type="button" class="link-btn" :disabled="busy" :aria-current="index === breadcrumbs.length - 1 ? 'location' : undefined" @click="run('list', crumb.path)">{{ crumb.label }}</button></template>
          </nav>
        </div>
        <div ref="documentList" class="document-list pane-scroll">
          <section v-if="mode === 'search'" class="search-results" aria-label="Brain search results">
            <StateMessage v-if="busy && operation === 'search'" kind="loading">Searching…</StateMessage>
            <StateMessage v-else-if="!searched" kind="empty" title="Search both brains">Find documents across your Personal Brain and the shared Instance Brain.</StateMessage>
            <StateMessage v-else-if="!error && hits.length === 0" kind="empty">No documents match your search. Try a different word.</StateMessage>
            <article v-for="hit in hits" :key="`${hit.scope}:${hit.path}:${hit.heading}`" class="search-hit">
              <ListRow class="hit-row" :active="document?.scope === hit.scope && document?.path === hit.path" :disabled="busy" :aria-label="hit.heading || fileName(hit.path)" @click="openHit(hit)">
                <span class="hit-title">{{ hit.heading || fileName(hit.path) }}</span>
                <span class="scope-badge status-badge">{{ scopeLabel(hit.scope) }} · {{ hit.scope === 'personal' ? 'Only you' : 'Shared' }}</span>
                <span class="hit-path">{{ hit.connection_label }} · {{ hit.path }} · {{ hit.refresh_status.replaceAll('_', ' ') }}</span>
              </ListRow>
              <MarkdownContent class="hit-preview" :text="hit.content" />
            </article>
          </section>
          <template v-else>
            <StateMessage v-if="busy && operation === 'list'" kind="loading">Loading folder…</StateMessage>
            <ul v-else-if="entries.length" class="file-list" aria-label="Brain documents">
              <li v-for="entry in entries" :key="entry.path">
                <ListRow class="file-row" :active="entry.path === document?.path" :disabled="busy" :aria-label="entry.path" :data-path="entry.path" @click="run(entry.kind === 'folder' ? 'list' : 'read', entry.path)">
                  <svg v-if="entry.kind === 'folder'" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h6l2 3h10v12H3z" /></svg>
                  <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>
                  <span class="file-copy"><strong>{{ fileName(entry.path) }}</strong><small>{{ entry.kind === 'folder' ? 'Folder' : 'Document' }}</small></span>
                  <span v-if="entry.kind === 'folder'" class="folder-arrow" aria-hidden="true">›</span>
                </ListRow>
              </li>
            </ul>
            <StateMessage v-else kind="empty">{{ listingAvailable ? 'This folder is empty.' : 'Choose a folder or check the connection.' }}</StateMessage>
          </template>
        </div>
        <div class="browser-tools">
          <details v-if="scope !== 'both'" class="open-path">
            <summary>Open a specific path <span aria-hidden="true">›</span></summary>
            <div class="dialog-form"><label>Vault-relative path<input v-model="path" maxlength="500" placeholder="Inbox/Example.md" :disabled="busy" /></label>
              <div class="path-actions"><button type="button" class="pill-btn ghost" :disabled="busy" @click="run('list')">Browse folder</button><button type="button" class="pill-btn ghost" :disabled="busy || !path.trim()" @click="run('read')">Read document</button></div>
            </div>
          </details>
          <details class="connection-tools">
            <summary>Connection &amp; settings <span aria-hidden="true">›</span></summary>
            <div class="connection-actions"><button type="button" class="link-btn" @click="connectionOpen = true">Personal connection</button><button type="button" class="link-btn" :disabled="busy || scope === 'both'" :aria-busy="busy && operation === 'status'" @click="run('status', '')">{{ busy && operation === 'status' ? 'Checking…' : 'Check connection' }}</button></div>
          </details>
          <div class="browser-footer">
            <span class="connection-status" role="status">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7v.2" /></svg>
              <template v-if="connectionStatus">Connection: {{ connectionStatus.status?.replaceAll('_', ' ') ?? 'unknown' }} · Index: {{ connectionStatus.index_status?.replaceAll('_', ' ') ?? 'not checked' }}</template>
              <template v-else>{{ scope === 'both' ? 'Search across shared and personal knowledge' : 'Connection not checked' }}</template>
            </span>
            <p>{{ scope === 'both' ? 'Results keep their original brain.' : scope === 'personal' ? 'Available only to your account.' : 'Readable by all signed-in users.' }}</p>
          </div>
        </div>
      </aside>
      <section class="reader" aria-label="Brain document reader">
        <header class="reader-head"><BackButton :disabled="busy" @click="showBrowser">All documents</BackButton><span class="reader-path">{{ document?.path || 'Document reader' }}</span><span v-if="document" class="reader-audience status-badge">{{ document.scope === 'personal' ? 'Only you' : 'Shared' }}</span></header>
        <div v-if="document" ref="readerContent" class="document-content pane-scroll" tabindex="0" aria-label="Document content">
          <div class="document-body"><p class="document-scope">{{ scopeLabel(document.scope) }}</p>
            <StateMessage v-if="busy && operation === 'read'" kind="loading">Opening document…</StateMessage>
            <MarkdownContent v-if="document.content" :text="document.content" />
            <StateMessage v-else kind="empty">This document is empty.</StateMessage>
          </div>
        </div>
        <div v-else class="reader-placeholder"><StateMessage v-if="busy && operation === 'read'" kind="loading">Opening document…</StateMessage><StateMessage v-else kind="empty" title="Knowledge, within reach">Choose a document to read, or search this brain.</StateMessage></div>
        <footer v-if="document" class="reader-footer"><span>Reading from the {{ scopeLabel(document.scope) }}</span><span>Read-only</span></footer>
      </section>
    </WorkspaceLayout>
    <BaseModal class="connection-modal" :open="connectionOpen" title="Personal connection" @close="closeConnection"><BrainConnectionForm scope="personal" /></BaseModal>
  </PageLayout>
</template>
<style scoped>
svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.brain-workspace { --workspace-columns: 360px minmax(0, 1fr); }
.browser { display: flex; flex-direction: column; min-height: 0; min-width: 0; padding: 20px 12px; border-right: 1px solid var(--border); background: color-mix(in srgb, var(--surface) 50%, var(--bg)); }
.scope-line { margin-bottom: 12px; flex-shrink: 0; }
.scope-line :deep(.segmented-control), .scope-line :deep(.segmented) { width: 100%; }
.scope-line :deep(button.segment) { flex: 1; padding-inline: 8px; }
.search-form { margin: 0 0 12px; flex-shrink: 0; }
.browser-head { padding-bottom: 12px; flex-shrink: 0; }
.breadcrumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 0 10px; font-size: .8em; color: var(--muted); }
.breadcrumbs button { min-width: 0; max-width: 100%; padding: 0; font-size: 1em; overflow-wrap: anywhere; }
.document-list { flex: 1; min-height: 0; }
.file-list { padding: 0; margin: 0; list-style: none; }
.file-list li { margin-bottom: 6px; border-bottom: 1px solid var(--border); }
button.file-row { flex-direction: row; align-items: flex-start; gap: 10px; }
.file-copy { min-width: 0; }
.file-row svg { color: var(--muted); margin-top: 2px; }
.file-copy strong { display: block; font-weight: 500; overflow-wrap: anywhere; }
.file-copy small { display: block; margin-top: 4px; color: var(--muted); font-size: .85em; }
.file-row.active svg { color: var(--accent); }
.folder-arrow { margin-left: auto; color: var(--muted); }
.browser-tools { padding: 14px 10px 0; flex-shrink: 0; max-height: 40%; overflow-y: auto; }
.browser-tools details { border-top: 1px solid var(--border); }
summary { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 0; cursor: pointer; font-size: .8em; color: var(--muted); list-style: none; }
summary::-webkit-details-marker { display: none; }
summary > span { flex-shrink: 0; }
.dialog-form { padding-bottom: 14px; }
.path-actions, .connection-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.connection-actions { padding-bottom: 12px; }
.browser-footer { display: flex; flex-direction: column; gap: 8px; padding-top: 14px; border-top: 1px solid var(--border); }
.connection-status { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: .75em; overflow-wrap: anywhere; }
.connection-status svg { width: 14px; height: 14px; }
.browser-footer p { margin: 0; color: var(--muted); font-size: .7em; }
.reader { display: flex; flex-direction: column; min-height: 0; min-width: 0; background: var(--bg); }
.reader-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 28px; border-bottom: 1px solid var(--border); font-size: .8em; color: var(--muted); flex-shrink: 0; }
.reader-path { min-width: 0; overflow-wrap: anywhere; }
.reader-audience { flex-shrink: 0; }
.document-content { flex: 1; min-height: 0; overflow-wrap: anywhere; line-height: 1.8; }
.document-body { max-width: 820px; padding: 30px 36px; margin-inline: auto; }
.document-body :deep(h1) { font-size: 1.7em; font-weight: 600; line-height: 1.35; letter-spacing: -.025em; }
.document-body :deep(h2) { font-size: 1.15em; font-weight: 600; margin-top: 26px; }
.document-body :deep(h3) { font-size: 1.05em; }
.document-body :deep(blockquote) { border-left: 3px solid var(--border); padding-left: 16px; margin-left: 0; color: var(--muted); }
.document-scope { margin: 0 0 16px; color: var(--accent); text-transform: uppercase; letter-spacing: .08em; font-size: .7em; }
.reader-footer { display: flex; justify-content: space-between; gap: 12px; padding: 14px 28px; border-top: 1px solid var(--border); color: var(--muted); font-size: .75em; flex-shrink: 0; }
.reader-placeholder { display: flex; flex: 1; align-items: center; justify-content: center; padding: 28px; text-align: center; }
.results-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; padding: 0 10px; color: var(--muted); font-size: .8em; }
.results-head button { font-size: 1em; }
.search-hit { padding-bottom: 16px; margin-bottom: 6px; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }
.hit-title { font-weight: 500; }
.scope-badge { align-self: flex-start; }
.hit-path { color: var(--muted); font-size: .8em; overflow-wrap: anywhere; }
.hit-preview { padding: 0 12px; font-size: .85em; overflow-wrap: anywhere; }
.feedback { max-height: 25%; min-height: 0; overflow: auto; padding-bottom: 12px; flex-shrink: 0; overflow-wrap: anywhere; font-size: .85em; }
.feedback p { margin: 4px 0; }
.connection-modal :deep(.brain-connection) { margin: 0; padding: 0; border: 0; background: transparent; }
.connection-modal :deep(h3) { font-size: 1em; }
.connection-modal :deep(p) { overflow-wrap: anywhere; }
@media (max-width: 900px) and (min-width: 768px) {
  .brain-workspace { --workspace-columns: 280px minmax(0, 1fr); }
  .document-body { padding: 24px; }
}
@media (max-width: 767px) {
  .brains :deep(.page-column) { padding: 18px 16px 12px; }
  .brains :deep(.page-head) { margin-bottom: 16px; }
  .brains :deep(.page-title) { margin: 0; }
  .brains :deep(.page-description) { display: none; }
  .brains.mobile-reading :deep(.page-head) { display: none; }
  .scope-line :deep(button.segment) { min-height: 44px; }
  .browser { border-right: 0; padding: 16px 10px; }
  .brain-workspace:not(.reading) .reader, .brain-workspace.reading .browser { display: none; }
  button.file-row { min-height: 76px; }
  .breadcrumbs button, summary, .browser-tools button { min-width: 44px; min-height: 44px; }
  .reader-head { padding: 12px 16px; }
  .reader-head .reader-path { display: none; }
  .document-body { padding: 24px 20px; }
  .reader-footer { padding: 12px 16px; font-size: .7em; }
  dialog.connection-modal { position: fixed; inset: auto 0 var(--rail-height); width: 100%; max-width: none; max-height: calc(100dvh - var(--rail-height) - env(safe-area-inset-top, 0px) - 16px); margin: 0; border-radius: var(--radius-xl); }
}
</style>
