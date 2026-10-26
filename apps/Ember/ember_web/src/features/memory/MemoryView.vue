<script setup lang="ts">
import ListEditorLayout from "../../components/layout/ListEditorLayout.vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import { computed, getCurrentInstance, onMounted, onUnmounted, ref, watch } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import { MEMORY_MAX, MEMORY_TEXT_MAX, memoryClient, type MemoryNote } from "./api/MemoryClient";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import "../../components/layout/infoPage.css";
import { errorMessage } from "../../utils/errors";

const memories = ref<MemoryNote[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");
const query = ref("");
const visible = ref(20);
const matches = computed(() => {
  const words = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return memories.value.filter((memory) => words.every((word) => memory.text.toLocaleLowerCase().includes(word)));
});
const shown = computed(() => matches.value.slice(0, visible.value));
watch(query, () => { visible.value = 20; }, { flush: "sync" });

async function load(): Promise<void> {
  if (!loading.value) loading.value = true;
  loadError.value = "";
  try { memories.value = await memoryClient.list(); }
  catch (error) { loadError.value = errorMessage(error); }
  finally { loading.value = false; }
}
onMounted(load);

const editorOpen = ref(false);
const editing = ref<MemoryNote | null>(null);
const text = ref("");
const formError = ref("");
const saving = ref(false);
const dirty = computed(() => editorOpen.value && text.value !== (editing.value?.text ?? ""));
const canSave = computed(() => dirty.value && text.value.trim() !== "" && text.value.length <= MEMORY_TEXT_MAX && !saving.value && !removing.value && (editing.value !== null || memories.value.length < MEMORY_MAX));
const discardOpen = ref(false);
type EditorTarget = MemoryNote | "new" | "close";
const discardTarget = ref<EditorTarget | null>(null);
let leaveAnswer: ((leave: boolean) => void) | null = null;

function showEditor(target: EditorTarget): void {
  const memory = typeof target === "object" ? target : null;
  editing.value = memory;
  text.value = memory?.text ?? "";
  formError.value = "";
  notice.value = "";
  editorOpen.value = target !== "close";
}
function go(target: EditorTarget): void {
  if (saving.value || removing.value) return;
  if (target === "new" && memories.value.length >= MEMORY_MAX) return;
  if (editorOpen.value && (target === "new" ? editing.value === null : typeof target === "object" && editing.value?.id === target.id)) return;
  if (dirty.value) { discardTarget.value = target; discardOpen.value = true; }
  else showEditor(target);
}
function openEditor(memory: MemoryNote | null = null): void {
  go(memory ?? "new");
}
function closeEditor(): void {
  go("close");
}
function answerDiscard(discard: boolean): void {
  discardOpen.value = false;
  if (discard) showEditor(discardTarget.value ?? "close");
  discardTarget.value = null;
  leaveAnswer?.(discard);
  leaveAnswer = null;
}
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) {
  onBeforeRouteLeave(() => {
    if (saving.value || removing.value) return false;
    if (!dirty.value) return true;
    discardTarget.value = null;
    discardOpen.value = true;
    return new Promise<boolean>((resolve) => { leaveAnswer = resolve; });
  });
}
function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value || saving.value || removing.value) { event.preventDefault(); event.returnValue = ""; }
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onUnmounted(() => { window.removeEventListener("beforeunload", beforeUnload); leaveAnswer?.(false); });

async function save(): Promise<void> {
  if (!canSave.value) return;
  saving.value = true;
  formError.value = "";
  try {
    const note = editing.value
      ? await memoryClient.update(editing.value.id, text.value, editing.value.text)
      : await memoryClient.create(text.value);
    memories.value = [note, ...memories.value.filter((memory) => memory.id !== note.id)];
    memories.value.sort((a, b) => b.id - a.id);
    query.value = "";
    // Keep the saved item visible, including an older memory edited beyond page one.
    visible.value = Math.max(20, memories.value.findIndex((memory) => memory.id === note.id) + 1);
    editing.value = note;
    text.value = note.text;
    notice.value = "Memory saved.";
  } catch (error) { formError.value = errorMessage(error); }
  finally { saving.value = false; }
}

const deleting = ref<MemoryNote | null>(null);
const removing = ref(false);
const removeError = ref("");
function askDelete(memory: MemoryNote): void { deleting.value = memory; removeError.value = ""; }
async function remove(): Promise<void> {
  if (!deleting.value || removing.value) return;
  removing.value = true;
  removeError.value = "";
  try {
    await memoryClient.remove(deleting.value.id);
    memories.value = memories.value.filter((memory) => memory.id !== deleting.value!.id);
    if (editing.value?.id === deleting.value.id) showEditor("close");
    deleting.value = null;
    notice.value = "Memory deleted.";
  } catch (error) { removeError.value = errorMessage(error); }
  finally { removing.value = false; }
}
</script>


<template>
  <PageLayout title="Memory" description="Review what Ember remembers about you." class="memory info-content" :class="{ 'memory-open': editorOpen }" wide fill>
    <template #actions><button type="button" class="primary" :disabled="loading || !!loadError || saving || removing || memories.length >= MEMORY_MAX" @click="openEditor()">Add memory</button></template>
    <div class="column">
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="loading" class="muted" role="status">Loading memories…</p>
      <div v-else-if="loadError" class="load-error" role="alert"><p>Could not load memories: {{ loadError }}</p><button type="button" class="chip" @click="load">Try again</button></div>
      <ListEditorLayout
        v-else
        class="layout"
        :editing="editorOpen"
        list-label="Memory list"
        editor-label="Memory editor"
        back-label="All memories"
        :busy="saving || removing"
        :saving="saving"
        :dirty="dirty"
        :can-save="canSave"
        show-saved-state
        @back="closeEditor"
        @submit="save"
      >
        <template #list>
          <div class="list-heading"><span>All memories</span><span>{{ memories.length }}/{{ MEMORY_MAX }}</span></div>
          <label class="memory-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg><input v-model="query" type="search" aria-label="Search memories" placeholder="Search memories…" /></label>
          <div class="list-scroll">
            <div class="memory-list" aria-label="Saved memories">
              <article v-if="editorOpen && !editing" class="draft-row"><button type="button" class="memory-row active" aria-current="true" :disabled="saving || removing" @click="openEditor()"><span class="memory-text">New memory</span><span class="memory-date">Not saved yet</span></button></article>
              <article v-for="memory in shown" :key="memory.id">
                <button type="button" :class="['memory-row', { active: editorOpen && editing?.id === memory.id }]" :aria-current="editorOpen && editing?.id === memory.id" :aria-label="'Edit memory ' + memory.id" :aria-describedby="'memory-summary-' + memory.id" :disabled="saving || removing" @click="openEditor(memory)">
                  <span :id="'memory-summary-' + memory.id" class="memory-text">{{ memory.text }}</span><span class="memory-date">Created <time :datetime="memory.created_at">{{ new Date(memory.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) }}</time></span>
                </button>
              </article>
            </div>
            <div v-if="memories.length === 0 && !(editorOpen && !editing)" class="empty"><h3>No saved memories yet.</h3><p>Add a useful fact, preference, or instruction for Ember to remember.</p></div>
            <div v-else-if="memories.length && matches.length === 0" class="empty"><h3>No memories match your search.</h3><p>Try a different word or clear your search.</p><button type="button" class="chip" @click="query = ''">Clear search</button></div>
            <footer v-if="matches.length" class="pagination"><p>Showing {{ shown.length }} of {{ matches.length }}</p><button v-if="shown.length < matches.length" type="button" class="chip" @click="visible += 20">Load more</button></footer>
            <p v-if="memories.length >= MEMORY_MAX" class="capacity-note">Memory is full. Delete a memory before adding another.</p>
          </div>
          <p class="memory-help">One useful fact, preference or instruction per memory.</p>
        </template>
        <template #head><span class="context-label"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 18V5M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4M17.6 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.6 1.5 4 4 0 0 0-2.8 5.6 4 4 0 0 0 .6 6.9A4 4 0 0 0 12 20a4 4 0 0 0 7.8-1 4 4 0 0 0 .6-6.9 4 4 0 0 0-2.8-5.6" /></svg>Remembered context</span></template>
        <template #editor>
            <div class="writing">
              <label class="body-field" for="memory-text"><span class="memory-label">{{ editing ? 'Memory' : 'New memory' }}</span></label>
              <textarea id="memory-text" v-model="text" aria-label="Memory" :maxlength="MEMORY_TEXT_MAX" :disabled="saving || removing" placeholder="One useful fact for Ember to remember…" autofocus />
              <p class="character-count">{{ text.length }}/{{ MEMORY_TEXT_MAX }} characters</p>
              <p v-if="editing" class="memory-created">Created <time :datetime="editing.created_at">{{ new Date(editing.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) }}</time></p>
              <p v-else class="memory-created">Not saved yet</p>
              <p class="writing-hint">Keep it short and specific. Edit this context when it no longer fits.</p>
            </div>
            <details v-if="editing" :key="editing.id" class="manage-memory"><summary>Manage memory <span aria-hidden="true">›</span></summary><div class="danger-zone"><b>Danger zone</b><button type="button" class="danger" :aria-label="'Delete memory ' + editing.id" :disabled="saving || removing" @click="askDelete(editing)">Delete memory</button></div></details>
            <p v-if="formError" class="error form-error" role="alert">{{ formError }}</p>
        </template>
        <template #placeholder><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4c-5-5-10 2-6 5-6 2-2 9 2 7-1 6 4 6 4 2V4zm0 0c5-5 10 2 6 5 6 2 2 9-2 7 1 6-4 6-4 2" /></svg><h3>Keep the useful context</h3><p>Pick a memory, or add a new one.</p><button type="button" class="chip" :disabled="memories.length >= MEMORY_MAX" @click="openEditor()">Create a memory</button></template>
      </ListEditorLayout>
    </div>
    <ConfirmModal :open="deleting !== null" title="Delete this memory?" :message="removeError || 'Ember will no longer remember this. This cannot be undone.'" confirm-label="Delete memory" danger :busy="removing" @confirm="remove" @close="!removing && (deleting = null)" />
    <ConfirmModal :open="discardOpen" title="Discard your changes?" message="This memory has changes you have not saved." confirm-label="Discard" danger @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
.column { display: flex; flex: 1; min-height: 0; flex-direction: column; }

.memory-search { display: flex; align-items: center; gap: 7px; padding: 8px 9px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); flex-shrink: 0; }
.memory-search svg { width: 16px; height: 16px; color: var(--muted); }
.memory-search input { min-width: 0; width: 100%; padding: 0; border: 0; background: transparent; color: var(--text); font: inherit; font-size: .8em; }
.memory-search:focus-within { border-color: var(--accent); }
.list-scroll { flex: 1; min-height: 0; overflow-y: auto; }
.memory-list { display: flex; flex-direction: column; gap: 6px; }
button.memory-row { display: flex; flex-direction: column; align-items: stretch; justify-content: flex-start; gap: 7px; width: 100%; padding: 14px 12px; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--text); background: transparent; font: inherit; font-size: .9em; text-align: left; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
button.memory-row:hover { background: var(--surface); }
button.memory-row.active { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
.memory-text { font-weight: 500; overflow-wrap: anywhere; white-space: pre-wrap; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.memory-date { color: var(--muted); font-size: .75em; }
.pagination { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; margin: 16px 10px 0; font-size: .75em; color: var(--muted); }
.pagination p { margin: 0; }
.memory-help { color: var(--muted); font-size: .7em; margin: 14px 10px 0; padding-top: 14px; border-top: 1px solid var(--border); flex-shrink: 0; }
.capacity-note { font-size: .8em; color: var(--muted); margin: 16px 10px 0; }
.empty { padding: 20px 10px; font-size: .85em; color: var(--muted); }
.empty h3 { font-size: 1em; font-weight: 500; margin: 0 0 8px; color: var(--text); }
.empty p { margin: 0 0 12px; }
.context-label { display: inline-flex; align-items: center; gap: 7px; font-size: .8em; color: var(--muted); }
.context-label svg { width: 15px; height: 15px; }
.context-label svg, .memory-search svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.writing { display: flex; flex-direction: column; flex: 1 0 auto; gap: 18px; min-height: 310px; padding: 30px 36px 20px; }
.memory-label { font-size: 1.35em; font-weight: 600; letter-spacing: -.015em; }
.writing textarea { flex: 1; width: 100%; min-width: 0; min-height: 200px; padding: 0; border: 0; border-radius: 0; color: var(--text); background: transparent; font: inherit; line-height: 1.9; resize: vertical; }
.character-count { align-self: flex-end; font-size: .75em; color: var(--muted); margin: 0; }
.memory-created { font-size: .75em; color: var(--muted); margin: 0; }
.writing-hint { font-size: .8em; color: var(--muted); margin: 0; max-width: 450px; }
.manage-memory { border-top: 1px solid var(--border); padding: 0 28px; flex-shrink: 0; }
summary { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 0; font-size: .85em; cursor: pointer; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary span { color: var(--muted); }
.form-error { margin: 12px 20px; font-size: .85em; }
@media (min-width: 1200px) { .writing { padding-inline: max(36px, calc((100% - 760px) / 2)); } }
@media (max-width: 900px) and (min-width: 768px) { .writing { padding-inline: 22px; } .manage-memory { padding-inline: 20px; } }
@media (max-width: 767px) {
  .memory :deep(.page-column) { padding: 18px 16px 12px; }
  .memory :deep(.page-head) { flex-direction: row; align-items: center; margin-bottom: 16px; gap: 10px; }
  .memory :deep(.page-title) { margin: 0; }
  .memory :deep(.page-description) { display: none; }
  .memory.memory-open :deep(.page-head) { display: none; }
  .memory :deep(.page-actions button) { min-height: 44px; }
  .memory-search { min-height: 44px; }
  button.memory-row { min-height: 100px; }
  .writing { min-height: 310px; padding: 24px 20px 18px; }
  .writing textarea { min-height: 250px; }
  .memory-label { font-size: 1.3em; }
  .manage-memory { padding-inline: 20px; }
}
</style>
