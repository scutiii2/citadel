<script setup lang="ts">
import { computed, getCurrentInstance, onMounted, onUnmounted, reactive, ref } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import { NOTE_BODY_MAX, NOTE_TITLE_MAX, NOTES_MAX, notesClient, type Note } from "../api/NotesClient";
import ConfirmModal from "../components/ConfirmModal.vue";
import "../components/infoPage.css";
import { errorMessage, formatUtc } from "../utils/errors";

/** The signed-in account's private notes (ember_api's /api/notes, kept in
 * db_gateway). A list on the left and an editor on the right; on a narrow
 * screen one at a time. Edits are a draft until Save. */

const NEW = "new";

const notes = ref<Note[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");

// The open note: a note id, NEW for one not saved yet, or null for none.
const selected = ref<string | null>(null);
const form = reactive({ title: "", body: "" });
const saved = reactive({ title: "", body: "" });
const saving = ref(false);
const removing = ref(false);
const formError = ref("");

const dirty = computed(() => selected.value !== null && (form.title !== saved.title || form.body !== saved.body));
const canSave = computed(() => form.title.trim() !== "" && dirty.value && !saving.value && !removing.value);
const atLimit = computed(() => notes.value.length >= NOTES_MAX);

async function load(): Promise<void> {
  try {
    notes.value = await notesClient.list();
    loadError.value = "";
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function show(target: string | null): void {
  selected.value = target;
  formError.value = "";
  notice.value = "";
  const note = target === null || target === NEW ? undefined : notes.value.find((n) => n.id === target);
  saved.title = form.title = note?.title ?? "";
  saved.body = form.body = note?.body ?? "";
}

// Leaving unsaved edits asks first; the target waits here meanwhile.
const discardTarget = ref<string | null | undefined>(undefined);
function go(target: string | null): void {
  if (target === selected.value) return;
  if (dirty.value) discardTarget.value = target;
  else show(target);
}
function discard(): void {
  const target = discardTarget.value;
  discardTarget.value = undefined;
  if (target !== undefined) show(target);
}

// Leaving the page with unsaved edits asks first, like the Settings page. The
// router waits on this answer; a mount without a router (unit tests) skips it.
const leaveOpen = ref(false);
let leaveAnswer: ((leave: boolean) => void) | null = null;
function answerLeave(leave: boolean): void {
  leaveOpen.value = false;
  leaveAnswer?.(leave);
  leaveAnswer = null;
}
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) {
  onBeforeRouteLeave(() => {
    if (saving.value || removing.value) return false;
    if (!dirty.value) return true;
    leaveOpen.value = true;
    return new Promise<boolean>((resolve) => (leaveAnswer = resolve));
  });
}
// Closing or reloading the tab gets the browser's own warning.
function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value || saving.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onUnmounted(() => {
  window.removeEventListener("beforeunload", beforeUnload);
  answerLeave(false);
});

function startNew(): void {
  if (atLimit.value) {
    notice.value = `You can keep at most ${NOTES_MAX} notes. Delete one to add another.`;
    return;
  }
  go(NEW);
}

async function save(): Promise<void> {
  if (!canSave.value || selected.value === null) return;
  saving.value = true;
  formError.value = "";
  try {
    const title = form.title.trim();
    const note =
      selected.value === NEW
        ? await notesClient.create(title, form.body)
        : await notesClient.update(selected.value, title, form.body);
    // The newest edit goes first, as the server lists them.
    notes.value = [note, ...notes.value.filter((n) => n.id !== note.id)];
    selected.value = note.id;
    saved.title = form.title = note.title;
    saved.body = form.body = note.body;
    notice.value = "Saved.";
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

const confirmDelete = ref(false);
async function remove(): Promise<void> {
  const id = selected.value;
  if (id === null || id === NEW || removing.value) return;
  removing.value = true;
  formError.value = "";
  try {
    await notesClient.remove(id);
    notes.value = notes.value.filter((n) => n.id !== id);
    show(null);
    notice.value = "Note deleted.";
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    removing.value = false;
    confirmDelete.value = false;
  }
}

function preview(note: Note): string {
  return note.body.trim().replace(/\s+/g, " ").slice(0, 80);
}
</script>

<template>
  <section class="info-page notes">
    <div class="column page-column">
      <div class="top">
        <div>
          <h2 class="page-title">Notes</h2>
          <p class="muted intro page-description">Private notes, just for your account.</p>
        </div>
        <button type="button" class="primary new-note" @click="startNew">New note</button>
      </div>

      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="loadError" class="error" role="alert">Could not load your notes: {{ loadError }}</p>
      <p v-if="loading" class="muted">Loading …</p>

      <div v-else-if="!loadError" :class="['layout', { editing: selected !== null }]">
        <div class="list-pane">
          <p v-if="notes.length === 0 && selected !== NEW" class="muted empty">You have no notes yet.</p>
          <ul v-else class="list" aria-label="Notes">
            <li v-if="selected === NEW">
              <button type="button" class="note-row active" aria-current="true">
                <span class="title">{{ form.title.trim() || "New note" }}</span>
                <span class="muted">Not saved yet</span>
              </button>
            </li>
            <li v-for="n in notes" :key="n.id">
              <button type="button" :class="['note-row', { active: n.id === selected }]" :aria-current="n.id === selected" @click="go(n.id)">
                <span class="title">{{ n.id === selected && form.title.trim() ? form.title.trim() : n.title }}</span>
                <span v-if="preview(n)" class="snippet">{{ preview(n) }}</span>
                <span class="muted">{{ formatUtc(n.updated_at) }}</span>
              </button>
            </li>
          </ul>
          <p class="muted count">{{ notes.length }}/{{ NOTES_MAX }} notes</p>
        </div>

        <form v-if="selected !== null" class="editor" @submit.prevent="save">
          <button type="button" class="chip back" @click="go(null)">‹ All notes</button>
          <label>
            Title
            <input v-model="form.title" type="text" :maxlength="NOTE_TITLE_MAX" aria-label="Title" :disabled="saving || removing" />
          </label>
          <label>
            Note
            <textarea v-model="form.body" rows="14" :maxlength="NOTE_BODY_MAX" aria-label="Note text" :disabled="saving || removing" />
            <span class="muted count">{{ form.body.length }}/{{ NOTE_BODY_MAX }}</span>
          </label>
          <p v-if="formError" class="error" role="alert">{{ formError }}</p>
          <div class="actions">
            <span v-if="dirty" class="unsaved" role="status"><i aria-hidden="true" />Unsaved changes</span>
            <button type="submit" class="primary" :disabled="!canSave" :aria-busy="saving">Save</button>
          </div>
          <div v-if="selected !== NEW" class="danger-zone">
            <b>Danger zone</b>
            <button type="button" class="danger" :disabled="saving || removing" @click="confirmDelete = true">Delete this note</button>
          </div>
        </form>
        <p v-else class="muted placeholder">Pick a note, or start a new one.</p>
      </div>
    </div>

    <ConfirmModal
      :open="confirmDelete"
      title="Delete this note?"
      message="This note will be gone for good."
      confirm-label="Delete note"
      danger
      :busy="removing"
      @confirm="remove"
      @close="confirmDelete = false"
    />
    <ConfirmModal
      :open="leaveOpen"
      title="Leave without saving?"
      message="This note has changes you have not saved."
      confirm-label="Leave page"
      danger
      @confirm="answerLeave(true)"
      @close="answerLeave(false)"
    />
    <ConfirmModal
      :open="discardTarget !== undefined"
      title="Discard your changes?"
      message="This note has changes you have not saved."
      confirm-label="Discard"
      danger
      @confirm="discard"
      @close="discardTarget = undefined"
    />
  </section>
</template>

<style scoped>
.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.notice {
  margin: 8px 0;
  color: var(--muted);
}
.layout {
  display: grid;
  grid-template-columns: minmax(200px, 270px) 1fr;
  gap: 16px;
  margin-top: 12px;
  align-items: start;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.note-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--surface);
  font: inherit;
  font-size: 0.9em;
  text-align: left;
  cursor: pointer;
}
.note-row:hover,
.note-row.active {
  border-color: var(--accent);
}
.title {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.snippet {
  color: var(--muted);
  overflow-wrap: anywhere;
}
.note-row .muted {
  font-size: 0.85em;
}
.count {
  margin: 6px 0 0;
  font-size: 0.8em;
}
.editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.editor label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.9em;
}
.editor textarea {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
  font: inherit;
  resize: vertical;
}
.actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.unsaved {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85em;
  color: var(--muted);
}
.unsaved i {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.danger-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-lg);
}
.back {
  display: none;
  align-self: flex-start;
}
.placeholder {
  margin: 0;
  padding: 24px 0;
}

/* Narrow screens: the list, or the open note, one at a time. */
@media (max-width: 700px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .layout.editing .list-pane,
  .layout:not(.editing) .placeholder {
    display: none;
  }
  .back {
    display: inline-block;
  }
}
</style>
