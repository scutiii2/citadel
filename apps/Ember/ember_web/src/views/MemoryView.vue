<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, getCurrentInstance, onMounted, onUnmounted, ref, watch } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import { MEMORY_MAX, MEMORY_TEXT_MAX, memoryClient, type MemoryNote } from "../api/MemoryClient";
import BaseModal from "../components/BaseModal.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

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
const canSave = computed(() => dirty.value && text.value.trim() !== "" && text.value.length <= MEMORY_TEXT_MAX && !saving.value);
const discardOpen = ref(false);
let leaveAnswer: ((leave: boolean) => void) | null = null;

function openEditor(memory: MemoryNote | null = null): void {
  editing.value = memory;
  text.value = memory?.text ?? "";
  formError.value = "";
  editorOpen.value = true;
}
function closeEditor(): void {
  if (saving.value) return;
  if (dirty.value) discardOpen.value = true;
  else editorOpen.value = false;
}
function answerDiscard(discard: boolean): void {
  discardOpen.value = false;
  if (discard) editorOpen.value = false;
  leaveAnswer?.(discard);
  leaveAnswer = null;
}
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) {
  onBeforeRouteLeave(() => {
    if (saving.value || removing.value) return false;
    if (!dirty.value) return true;
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
    editorOpen.value = false;
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
    deleting.value = null;
    notice.value = "Memory deleted.";
  } catch (error) { removeError.value = errorMessage(error); }
  finally { removing.value = false; }
}
</script>

<template>
  <PageLayout title="Memory" description="Review the context Ember remembers about you." class="memory info-content">
    <template #actions>
      <button type="button" class="primary" :disabled="loading || !!loadError || memories.length >= MEMORY_MAX" @click="openEditor()">Add memory</button>
    </template>
    <div class="column">
      <p v-if="notice" class="muted" role="status">{{ notice }}</p>
      <p v-if="loading" class="muted" role="status">Loading memories…</p>
      <div v-else-if="loadError" class="load-error" role="alert">
        <p>Could not load memories: {{ loadError }}</p>
        <button type="button" class="chip" @click="load">Try again</button>
      </div>
      <template v-else>
        <label class="page-search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
          <input v-model="query" type="search" aria-label="Search memories" placeholder="Search memories…" />
        </label>
        <p class="search-count">{{ memories.length }}/{{ MEMORY_MAX }} memories</p>
        <p v-if="memories.length === 0" class="muted empty">No saved memories yet.</p>
        <p v-else-if="matches.length === 0" class="muted empty">No memories match your search.</p>
        <div v-else class="memory-list" aria-label="Saved memories">
          <article v-for="memory in shown" :key="memory.id" class="card">
            <div class="card-head">
              <p class="memory-text">{{ memory.text }}</p>
              <div class="row-actions">
                <button type="button" class="chip" :aria-label="`Edit memory ${memory.id}`" @click="openEditor(memory)">Edit</button>
                <button type="button" class="danger" :aria-label="`Delete memory ${memory.id}`" @click="askDelete(memory)">Delete</button>
              </div>
            </div>
            <p class="memory-date">Created {{ new Date(memory.created_at).toLocaleString() }}</p>
          </article>
        </div>
        <footer v-if="matches.length" class="pagination">
          <p class="muted">Showing {{ shown.length }} of {{ matches.length }} memories</p>
          <button v-if="shown.length < matches.length" type="button" class="chip" @click="visible += 20">Load more</button>
        </footer>
        <p v-if="memories.length >= MEMORY_MAX" class="muted">Memory is full. Delete a memory before adding another.</p>
      </template>
    </div>
    <BaseModal :open="editorOpen" :title="editing ? 'Edit memory' : 'Add memory'" @close="closeEditor">
      <form class="memory-form info-page" @submit.prevent="save">
        <p class="page-description">Save one short fact, preference or instruction for Ember to remember.</p>
        <label for="memory-text">Memory</label>
        <textarea id="memory-text" v-model="text" rows="5" :maxlength="MEMORY_TEXT_MAX" :disabled="saving" autofocus />
        <p class="character-count muted">{{ text.length }}/{{ MEMORY_TEXT_MAX }} characters</p>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="form-actions">
          <button type="button" class="chip" :disabled="saving" @click="closeEditor">Cancel</button>
          <button type="submit" class="primary" :disabled="!canSave" :aria-busy="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
        </div>
      </form>
    </BaseModal>
    <ConfirmModal :open="deleting !== null" title="Delete this memory?"
      :message="removeError || 'Ember will no longer remember this. This cannot be undone.'"
      confirm-label="Delete memory" danger :busy="removing" @confirm="remove" @close="!removing && (deleting = null)" />
    <ConfirmModal :open="discardOpen" title="Discard your changes?" message="This memory has changes you have not saved."
      confirm-label="Discard" danger @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
.memory-list { display: flex; flex-direction: column; gap: 12px; }
.memory-list .card { margin: 0; }
.memory-text { flex: 1; min-width: 0; margin: 0; overflow-wrap: anywhere; }
.memory-date { margin: 10px 0 0; color: var(--muted); font-size: 0.85em; }
.row-actions { display: flex; gap: 8px; flex-shrink: 0; }
.pagination { text-align: center; font-size: 0.85em; margin-top: 20px; }
.empty { padding: 24px 0; }
.load-error { color: var(--danger); }
.memory-form { display: flex; flex-direction: column; gap: 8px; overflow: visible; }
.memory-form textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; resize: vertical; }
.character-count { margin: 0; font-size: 0.8em; text-align: right; }
.form-actions { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 12px; }
button:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 767px) {
  .memory .card-head { flex-direction: column; }
  .row-actions { align-self: flex-end; }
}
</style>
