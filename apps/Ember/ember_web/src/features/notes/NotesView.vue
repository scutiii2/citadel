<script setup lang="ts">
import WorkspaceLayout from "../../components/layout/WorkspaceLayout.vue";
import NotePromotionPanel from "./components/NotePromotionPanel.vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import { computed, getCurrentInstance, onMounted, onUnmounted, reactive, ref, useId } from "vue";
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
} from "./api/NotesClient";
import { ApiError } from "../../api/http";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import "../../components/layout/infoPage.css";
import TagInput from "../../components/ui/forms/TagInput.vue";
import ToggleSwitch from "../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage, formatUtc } from "../../utils/errors";

/** The signed-in account's private notes (ember_api's /api/notes, kept in
 * db_gateway). A list on the left and an editor on the right; on a narrow
 * screen one at a time. Edits are a draft until Save. Each note has tags and a
 * switch that says whether agents may read it. */

const NEW = "new";
const mobileToolsOpen = ref(false);

const notes = ref<Note[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");

// The open note: a note id, NEW for one not saved yet, or null for none.
const selected = ref<string | null>(null);
const publicationTarget = useId();
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
  mobileToolsOpen.value = false;
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
  <PageLayout class="notes info-content" :class="{ 'note-open': selected !== null }" title="Notes" description="Your thoughts, kept close." wide fill>
    <template #actions>
      <button type="button" class="primary new-note" :disabled="saving || removing" @click="startNew">New note</button>
    </template>
    <div class="column">

      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="loadError" class="error" role="alert">Could not load your notes: {{ loadError }}</p>
      <p v-if="loading" class="muted">Loading …</p>

      <WorkspaceLayout v-else-if="!loadError" :class="['layout', { editing: selected !== null }]">
        <div class="list-pane">
          <div class="list-heading"><span>All notes</span><span>{{ notes.length }}/{{ NOTES_MAX }} notes</span></div>
          <p v-if="notes.length === 0 && selected !== NEW" class="muted empty">You have no notes yet.</p>
          <ul v-else class="list" aria-label="Notes">
            <li v-if="selected === NEW">
              <button type="button" class="note-row active" aria-current="true">
                <span class="title">{{ form.title.trim() || "New note" }}</span>
                <span class="muted">Not saved yet</span>
              </button>
            </li>
            <li v-for="n in notes" :key="n.id">
              <button type="button" :class="['note-row', { active: n.id === selected }]" :aria-current="n.id === selected" :disabled="saving || removing" @click="go(n.id)">
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
          <details v-if="selected === null" class="library-publishing">
            <summary>Obsidian &amp; publishing <span aria-hidden="true">›</span></summary>
            <div :id="`${publicationTarget}-library`" />
          </details>
        </div>

        <form v-if="selected !== null" class="editor" @submit.prevent="save">
          <div class="editor-head">
            <button type="button" class="chip back" :disabled="saving || removing" @click="go(null)">‹ All notes</button>
            <span class="privacy"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3" /></svg>{{ form.agentReadable ? "Agents can read" : "Private note" }}</span>
          </div>
          <div class="editor-scroll">
          <div class="writing">
          <p v-if="savedEditor === 'agent'" class="agent-edit-note">
            An agent last changed this note. Saving your own changes removes this mark.
          </p>
          <label class="title-field">
            <span class="sr-only">Title</span>
            <input v-model="form.title" type="text" :maxlength="NOTE_TITLE_MAX" aria-label="Title" placeholder="Untitled note" :disabled="saving || removing" />
          </label>
          <label class="body-field">
            <span class="sr-only">Note</span>
            <textarea v-model="form.body" rows="10" placeholder="Start writing…" :maxlength="NOTE_BODY_MAX" aria-label="Note text" :disabled="saving || removing" />
            <span class="muted count">{{ form.body.length }}/{{ NOTE_BODY_MAX }}</span>
          </label>
          </div>
          <button type="button" class="mobile-tools-toggle" :aria-expanded="mobileToolsOpen" aria-controls="note-tools" @click="mobileToolsOpen = !mobileToolsOpen">Note details &amp; tools <span aria-hidden="true">{{ mobileToolsOpen ? "⌃" : "⌄" }}</span></button>
          <div id="note-tools" :class="['note-tools', { expanded: mobileToolsOpen }]">
          <details class="tag-tools">
            <summary><span>Tags</span><span class="summary-hint">{{ form.tags.join(", ") || "Add tags" }} <span aria-hidden="true">›</span></span></summary>
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
          </details>
          <details class="agent-tools">
            <summary><span>Agent access</span><span class="summary-hint">{{ form.agentReadable ? "Agents can read" : "Only you" }} <span aria-hidden="true">›</span></span></summary>
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
          </details>
          <details class="publishing-tools">
            <summary><span>Obsidian &amp; publishing</span><span aria-hidden="true">›</span></summary>
      <div :id="`${publicationTarget}-editor`" />
          </details>
          <details v-if="selected !== NEW" class="manage-tools">
            <summary>Manage note <span aria-hidden="true">›</span></summary>
            <div class="danger-zone">
              <b>Danger zone</b>
              <button type="button" class="danger" :disabled="saving || removing" @click="confirmDelete = true">Delete this note</button>
            </div>
          </details>
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
          </div>
          <div class="actions">
            <span v-if="dirty" class="unsaved" role="status"><i aria-hidden="true" />Unsaved changes</span>
            <button type="submit" class="primary" :disabled="!canSave" :aria-busy="saving">{{ saving ? "Saving…" : "Save" }}</button>
          </div>
        </form>
        <div v-else class="placeholder">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6" /></svg>
          <h3>A little room to think</h3><p>Pick a note, or start a new one.</p>
          <button type="button" class="chip" @click="startNew">Create a note</button>
        </div>
      </WorkspaceLayout>
    </div>

    <Teleport v-if="!loading && !loadError" :to="`#${publicationTarget}-${selected === null ? 'library' : 'editor'}`">
      <NotePromotionPanel :note-id="selected && selected !== NEW ? selected : null" :dirty="dirty" :source-version="JSON.stringify([openedAt, saved.title, saved.body, saved.tags])" />
    </Teleport>

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
.column { display: flex; flex: 1; min-height: 0; flex-direction: column; }
.notice { margin: 0 0 12px; color: var(--muted); font-size: .9em; }

.list-pane { min-width: 0; overflow-y: auto; background: color-mix(in srgb, var(--surface) 50%, var(--bg)); border-right: 1px solid var(--border); padding: 20px 12px; }
.list-heading { display: flex; justify-content: space-between; gap: 10px; padding: 0 10px 16px; font-size: .75em; color: var(--muted); }
.list-heading > :first-child { text-transform: uppercase; letter-spacing: .08em; }
.list { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; }
.empty { padding: 8px 10px; font-size: .9em; }
.new-note { flex-shrink: 0; min-height: 40px; }
.note-row { display: flex; flex-direction: column; gap: 7px; width: 100%; padding: 14px 12px; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--text); background: transparent; font: inherit; font-size: .9em; text-align: left; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
.note-row:hover { background: var(--surface); }
.note-row.active { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
.title { font-weight: 600; overflow-wrap: anywhere; }
.snippet { color: var(--muted); overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.note-row .muted { font-size: .8em; }
.row-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 7px; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); background: var(--surface); font-size: .8em; overflow-wrap: anywhere; }
.agent-mark { border-color: var(--warning); color: var(--warning); }
.editor { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--bg); }
.editor-head { display: flex; align-items: center; gap: 16px; padding: 16px 28px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.privacy { display: inline-flex; gap: 7px; align-items: center; font-size: .8em; color: var(--muted); }
.privacy svg, .placeholder svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.privacy svg { width: 15px; height: 15px; }
.editor-scroll { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; overflow-wrap: anywhere; scroll-padding: 20px; }
.writing { display: flex; flex-direction: column; flex: 1 0 auto; gap: 18px; min-height: 310px; padding: 30px 36px 20px; }
.title-field, .body-field { display: flex; flex-direction: column; min-width: 0; }
.notes .editor .title-field input { width: 100%; padding: 0; border: 0; border-radius: 0; background: transparent; font-size: 1.65em; font-weight: 600; letter-spacing: -.025em; line-height: 1.4; }
.body-field { flex: 1; gap: 12px; }
.editor textarea { width: 100%; min-height: 230px; padding: 0; border: 0; border-radius: 0; background: transparent; color: var(--text); font: inherit; line-height: 1.9; resize: vertical; }
.count { align-self: flex-end; font-size: .75em; color: var(--muted); }
.note-tools { flex-shrink: 0; border-top: 1px solid var(--border); padding: 0 28px; }
.note-tools > details + details { border-top: 1px solid var(--border); }
summary { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 0; font-size: .85em; cursor: pointer; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary > [aria-hidden], .summary-hint { color: var(--muted); }
.summary-hint { font-size: .9em; min-width: 0; text-align: right; overflow-wrap: anywhere; }
.summary-hint > span { margin-left: 12px; }
.note-tools details[open] > summary { color: var(--accent); }
.field, .agent-access { display: flex; flex-direction: column; gap: 12px; padding: 0 0 16px; }
.field-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.field-label { margin-right: auto; font-size: .85em; color: var(--muted); }
.suggestions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.tag.pick { font: inherit; font-size: .8em; cursor: pointer; }
.tag.pick:hover { border-color: var(--accent); }
.conflict { display: flex; flex-direction: column; gap: 8px; margin: 12px 20px; padding: 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .9em; }
.conflict p { margin: 0; }
.conflict-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.agent-edit-note, .agent-warning { margin: 0; padding: 10px 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .85em; }
.agent-warning { background: color-mix(in srgb, var(--warning) 12%, var(--bg)); }
.editor-scroll > .error { margin: 12px 20px; }
.actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 14px 28px; border-top: 1px solid var(--border); flex-shrink: 0; background: var(--bg); }
.actions .primary { min-width: 76px; min-height: 40px; }
.actions .primary[aria-busy="true"]::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 7px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); vertical-align: -1px; animation: save-spin .7s linear infinite; }
@keyframes save-spin { to { transform: rotate(360deg); } }
.unsaved { display: inline-flex; align-items: center; gap: 7px; margin-right: auto; font-size: .8em; color: var(--muted); }
.unsaved i { width: 6px; height: 6px; border-radius: var(--radius-full); background: var(--accent); flex-shrink: 0; }
.danger-zone { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-lg); font-size: .85em; }
.back, .mobile-tools-toggle { display: none; }
.placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 28px; color: var(--muted); text-align: center; }
.placeholder svg { width: 34px; height: 34px; color: var(--accent); }
.placeholder h3 { color: var(--text); }
.placeholder p { margin: 0 0 8px; font-size: .9em; }
.library-publishing { margin: 24px 10px 0; border-top: 1px solid var(--border); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
.notes button:focus-visible, .notes summary:focus-visible, .editor input:focus-visible, .editor textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (min-width: 1200px) { .writing { padding-inline: max(36px, calc((100% - 760px) / 2)); } }
@media (max-width: 900px) and (min-width: 768px) { .layout { --workspace-columns: 220px minmax(0, 1fr); } .writing { padding-inline: 22px; } .note-tools, .actions { padding-inline: 20px; } }
@media (max-width: 767px) {
  .notes :deep(.page-column) { padding: 18px 16px 12px; }
  .notes :deep(.page-head) { flex-direction: row; align-items: center; margin-bottom: 16px; gap: 10px; }
  .notes :deep(.page-title) { margin: 0; }
  .notes :deep(.page-description) { display: none; }
  .notes.note-open :deep(.page-head) { display: none; }
  .layout.editing .list-pane, .layout:not(.editing) .placeholder { display: none; }
  .list-pane { border-right: 0; padding: 16px 10px; }
  .note-row { min-height: 100px; }
  .editor-head { padding: 12px 16px; justify-content: space-between; gap: 10px; }
  .back { display: inline-block; min-height: 40px; }
  .writing { min-height: 310px; padding: 24px 20px 18px; }
  .notes .editor .title-field input { font-size: 1.45em; }
  .editor textarea { min-height: 250px; }
  .mobile-tools-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 15px 20px; border: 0; border-top: 1px solid var(--border); border-radius: 0; background: var(--bg); font: inherit; font-size: .85em; cursor: pointer; }
  .note-tools { display: none; padding-inline: 20px; }
  /* Keep an open publication dialog visible when resizing from desktop. */
  .note-tools.expanded, .note-tools:has(dialog[open]) { display: block; }
  .actions { padding: 12px 16px; }
}
</style>
