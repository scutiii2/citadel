<script setup lang="ts">
import NotePromotionPanel from "../components/NotePromotionPanel.vue";
import PageLayout from "../components/PageLayout.vue";
import { computed, getCurrentInstance, onMounted, onUnmounted, reactive, ref } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import {
  NOTE_BODY_MAX,
  NOTE_TAG_MAX,
  NOTE_TAGS_MAX,
  NOTE_TITLE_MAX,
  NOTES_MAX,
  normalizeTag,
  notesClient,
  type Note,
  type TagSuggestions,
} from "../api/NotesClient";
import { ApiError } from "../api/http";
import ConfirmModal from "../components/ConfirmModal.vue";
import "../components/infoPage.css";
import TagInput from "../components/TagInput.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage, formatUtc } from "../utils/errors";

/** The signed-in account's private notes (ember_api's /api/notes, kept in
 * db_gateway). A list on the left and an editor on the right; on a narrow
 * screen one at a time. Edits are a draft until Save. Each note has tags and a
 * switch that says whether agents may read it. */

const NEW = "new";

const notes = ref<Note[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");

// The open note: a note id, NEW for one not saved yet, or null for none.
const selected = ref<string | null>(null);
const form = reactive({ title: "", body: "", tags: [] as string[], agentReadable: false });
const saved = reactive({ title: "", body: "", tags: [] as string[], agentReadable: false });
// What is typed in the tag box but not added yet (TagInput's v-model:text) and the component itself.
const tagInput = ref("");
const tagField = ref<InstanceType<typeof TagInput> | null>(null);
// Who saved the open note last. Not part of the draft: only a save from this page changes it.
const savedEditor = ref<Note["last_editor"]>("user");
// The updated_at of the version the editor opened. A save sends it, so the server can refuse to
// overwrite a change made since (by an agent, or this note open in another tab).
const openedAt = ref("");
// The newer version the server holds, while a refused save waits for the user's choice.
const conflict = ref<Note | null>(null);
const saving = ref(false);
const removing = ref(false);
const formError = ref("");

const sameTags = (a: string[], b: string[]) => a.length === b.length && a.every((tag, i) => tag === b[i]);
// A tag typed but not added yet counts as an unsaved edit, so it is never lost silently.
const dirty = computed(
  () =>
    selected.value !== null &&
    (form.title !== saved.title ||
      form.body !== saved.body ||
      form.agentReadable !== saved.agentReadable ||
      !sameTags(form.tags, saved.tags) ||
      tagInput.value.trim() !== ""),
);
const canSave = computed(
  () => form.title.trim() !== "" && dirty.value && !saving.value && !removing.value && conflict.value === null,
);
const atLimit = computed(() => notes.value.length >= NOTES_MAX);

// The tags this account already uses (not on the open note yet), most used first: the input's suggestions.
const knownTags = computed(() => {
  const counts = new Map<string, number>();
  for (const note of notes.value) for (const tag of note.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  return [...counts]
    .filter(([tag]) => !form.tags.includes(tag))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tag, count]) => ({ tag, count }));
});

// Laya's suggestions: existing tags that may fit this note. Nothing is applied until the user picks one.
const suggestion = ref<TagSuggestions | null>(null);
const suggesting = ref(false);
const suggestError = ref("");
let suggestRun = 0; // a late answer for a note the user has left is dropped
const canSuggest = computed(
  () => knownTags.value.length > 0 && !suggesting.value && (form.title.trim() !== "" || form.body.trim() !== ""),
);
const suggestedTags = computed(() => (suggestion.value?.suggested ?? []).filter((tag) => !form.tags.includes(tag)));

async function suggest(): Promise<void> {
  if (!canSuggest.value) return;
  tagField.value?.commit();
  const run = ++suggestRun;
  suggesting.value = true;
  suggestError.value = "";
  suggestion.value = null;
  try {
    const found = await notesClient.suggestTags({ title: form.title, body: form.body, tags: [...form.tags] });
    if (run === suggestRun) suggestion.value = found;
  } catch (err) {
    if (run === suggestRun) suggestError.value = errorMessage(err);
  } finally {
    if (run === suggestRun) suggesting.value = false;
  }
}

// New tags written by a light model (tag-writer). Like suggestions, nothing is applied until the user picks one.
const generated = ref<string[] | null>(null);
const generating = ref(false);
const generateError = ref("");
let generateRun = 0;
const canGenerate = computed(() => !generating.value && (form.title.trim() !== "" || form.body.trim() !== ""));
const generatedTags = computed(() => (generated.value ?? []).filter((tag) => !form.tags.includes(tag)));

async function generate(): Promise<void> {
  if (!canGenerate.value) return;
  tagField.value?.commit();
  const run = ++generateRun;
  generating.value = true;
  generateError.value = "";
  generated.value = null;
  try {
    const made = await notesClient.generateTags({ title: form.title, body: form.body, tags: [...form.tags] });
    if (run === generateRun) generated.value = made.tags;
  } catch (err) {
    if (run === generateRun) generateError.value = errorMessage(err);
  } finally {
    if (run === generateRun) generating.value = false;
  }
}
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
  fillEditor(note);
}
/** Fills the editor, and what counts as saved, from a note (or empty). */
function fillEditor(note: Note | undefined): void {
  saved.title = form.title = note?.title ?? "";
  saved.body = form.body = note?.body ?? "";
  form.tags = [...(note?.tags ?? [])];
  saved.tags = [...form.tags];
  saved.agentReadable = form.agentReadable = note?.agent_readable ?? false;
  savedEditor.value = note?.last_editor ?? "user";
  openedAt.value = note?.updated_at ?? "";
  conflict.value = null;
  tagInput.value = "";
  suggestRun++; // an answer still on its way belongs to the note that was open
  suggestion.value = null;
  suggestError.value = "";
  suggesting.value = false;
  generateRun++;
  generated.value = null;
  generateError.value = "";
  generating.value = false;
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
  if (selected.value === null) return;
  tagField.value?.commit(); // a tag still in the box is part of the note
  if (tagInput.value.trim() !== "") return; // it could not be added (too many tags): its message is showing
  if (!canSave.value) return;
  saving.value = true;
  formError.value = "";
  try {
    const draft = {
      title: form.title.trim(),
      body: form.body,
      tags: [...form.tags],
      agent_readable: form.agentReadable,
    };
    const note =
      selected.value === NEW
        ? await notesClient.create(draft)
        : await notesClient.update(selected.value, draft, openedAt.value);
    // The newest edit goes first, as the server lists them.
    notes.value = [note, ...notes.value.filter((n) => n.id !== note.id)];
    selected.value = note.id;
    fillEditor(note);
    notice.value = "Saved.";
  } catch (err) {
    if (err instanceof ApiError && err.status === 412 && selected.value !== null && selected.value !== NEW) {
      await loadConflict(selected.value);
    } else {
      formError.value = errorMessage(err);
    }
  } finally {
    saving.value = false;
  }
}

/** The server refused a save because the note changed: fetch its newer version and ask what to do. */
async function loadConflict(id: string): Promise<void> {
  try {
    conflict.value = await notesClient.get(id);
  } catch (err) {
    formError.value = errorMessage(err);
  }
}
/** Drops the user's edits for the newer version. */
function showTheirs(): void {
  const theirs = conflict.value;
  if (theirs === null) return;
  notes.value = notes.value.some((n) => n.id === theirs.id)
    ? notes.value.map((n) => (n.id === theirs.id ? theirs : n))
    : [theirs, ...notes.value];
  fillEditor(theirs);
  notice.value = "Showing the newer version.";
}
/** Saves the user's edits over the newer version. */
async function keepMine(): Promise<void> {
  const theirs = conflict.value;
  if (theirs === null) return;
  openedAt.value = theirs.updated_at;
  conflict.value = null;
  await save();
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
  <PageLayout class="notes info-content" title="Notes" description="Private notes, just for your account.">
    <template #actions>
      <button type="button" class="primary new-note" @click="startNew">New note</button>
    </template>
    <div class="column">
      <NotePromotionPanel :note-id="selected && selected !== NEW ? selected : null" :dirty="dirty" :source-version="JSON.stringify([openedAt, saved.title, saved.body, saved.tags])" />

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
                <span v-if="n.tags.length || n.agent_readable || n.last_editor === 'agent'" class="row-tags">
                  <span v-for="tag in n.tags" :key="tag" class="tag">{{ tag }}</span>
                  <span v-if="n.agent_readable" class="tag agent-mark">Agents can read</span>
                  <span v-if="n.last_editor === 'agent'" class="tag agent-mark">Agent edit</span>
                </span>
                <span class="muted">{{ formatUtc(n.updated_at) }}</span>
              </button>
            </li>
          </ul>
          <p class="muted count">{{ notes.length }}/{{ NOTES_MAX }} notes</p>
        </div>

        <form v-if="selected !== null" class="editor" @submit.prevent="save">
          <button type="button" class="chip back" @click="go(null)">‹ All notes</button>
          <p v-if="savedEditor === 'agent'" class="agent-edit-note">
            An agent last changed this note. Saving your own changes removes this mark.
          </p>
          <label>
            Title
            <input v-model="form.title" type="text" :maxlength="NOTE_TITLE_MAX" aria-label="Title" :disabled="saving || removing" />
          </label>
          <div class="field">
            <div class="field-head">
              <span class="field-label">Tags</span>
              <button
                v-if="knownTags.length"
                type="button"
                class="chip"
                :disabled="!canSuggest"
                :aria-busy="suggesting"
                title="Ask Laya, a local model, which of your existing tags fit this note"
                @click="suggest"
              >
                {{ suggesting ? "Suggesting …" : "Suggest tags" }}
              </button>
              <button
                type="button"
                class="chip"
                :disabled="!canGenerate"
                :aria-busy="generating"
                title="Ask a light model to write up to three new tags for this note"
                @click="generate"
              >
                {{ generating ? "Generating …" : "Generate tag" }}
              </button>
            </div>
            <TagInput
              :key="selected ?? ''"
              ref="tagField"
              v-model="form.tags"
              v-model:text="tagInput"
              :known="knownTags"
              :normalize="normalizeTag"
              :max="NOTE_TAGS_MAX"
              :max-length="NOTE_TAG_MAX"
              :disabled="saving || removing"
            />
            <div v-if="suggestion" class="suggestions" role="status">
              <template v-if="suggestedTags.length">
                <span class="muted">Laya suggests:</span>
                <button
                  v-for="tag in suggestedTags"
                  :key="tag"
                  type="button"
                  class="tag pick"
                  :aria-label="`Add suggested tag ${tag}`"
                  @click="tagField?.add(tag)"
                >
                  + {{ tag }}
                </button>
              </template>
              <span v-else class="muted">None of your other tags seem to fit this note.</span>
              <span v-if="suggestion.skipped" class="muted">
                {{ suggestion.skipped }} of your tags {{ suggestion.skipped === 1 ? "was" : "were" }} not checked.
              </span>
            </div>
            <p v-if="suggestError" class="error" role="alert">{{ suggestError }}</p>
            <div v-if="generated" class="suggestions" role="status">
              <template v-if="generatedTags.length">
                <span class="muted">New tags:</span>
                <button
                  v-for="tag in generatedTags"
                  :key="tag"
                  type="button"
                  class="tag pick"
                  :aria-label="`Add generated tag ${tag}`"
                  @click="tagField?.add(tag)"
                >
                  + {{ tag }}
                </button>
              </template>
              <span v-else class="muted">No new tag came to mind for this note.</span>
            </div>
            <p v-if="generateError" class="error" role="alert">{{ generateError }}</p>
          </div>
          <label>
            Note
            <textarea v-model="form.body" rows="14" :maxlength="NOTE_BODY_MAX" aria-label="Note text" :disabled="saving || removing" />
            <span class="muted count">{{ form.body.length }}/{{ NOTE_BODY_MAX }}</span>
          </label>
          <div class="agent-access">
            <ToggleSwitch
              :checked="form.agentReadable"
              :disabled="saving || removing"
              @change="form.agentReadable = ($event.target as HTMLInputElement).checked"
            >
              Let agents read this note
            </ToggleSwitch>
            <p v-if="form.agentReadable" class="agent-warning" role="note">
              Agents can read this note. Be careful what you put in it: do not store passwords, keys or other private data.
            </p>
          </div>
          <p v-if="formError" class="error" role="alert">{{ formError }}</p>
          <div v-if="conflict" class="conflict" role="alert">
            <p>
              {{ conflict.last_editor === "agent" ? "An agent" : "Another session" }} changed this note after you opened
              it.
            </p>
            <div class="conflict-actions">
              <button type="button" class="chip" @click="showTheirs">Show their version (drops my changes)</button>
              <button type="button" class="chip" @click="keepMine">Save mine anyway</button>
            </div>
          </div>
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
  </PageLayout>
</template>

<style scoped>
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
.list-pane,
.editor { min-width: 0; }
.new-note { flex-shrink: 0; }
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
.row-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  color: var(--text);
  background: var(--bg);
  font-size: 0.8em;
}
.agent-mark {
  border-color: var(--warning);
  color: var(--warning);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.9em;
}
.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.tag.pick {
  color: var(--text);
  font: inherit;
  font-size: 0.8em;
  cursor: pointer;
}
.tag.pick:hover {
  border-color: var(--accent);
}
.agent-access {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.conflict {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--warning);
  border-radius: var(--radius-md);
  font-size: 0.9em;
}
.conflict p {
  margin: 0;
}
.conflict-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.agent-edit-note {
  margin: 0;
  padding: 6px 10px;
  border: 1px solid var(--warning);
  border-radius: var(--radius-md);
  color: var(--text);
  font-size: 0.85em;
}
.agent-warning {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--warning);
  border-radius: var(--radius-md);
  color: var(--text);
  background: color-mix(in srgb, var(--warning) 12%, var(--bg));
  font-size: 0.9em;
}
.editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.editor input { width: 100%; }
.editor textarea { width: 100%; min-height: 280px; }
.notes button:focus-visible,
.editor input:focus-visible,
.editor textarea:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
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
@media (max-width: 767px) {
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
