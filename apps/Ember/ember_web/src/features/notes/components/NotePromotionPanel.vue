<script setup lang="ts">
import { computed, getCurrentInstance, onMounted, onUnmounted, ref, watch } from "vue";
import { onBeforeRouteLeave, routerKey } from "vue-router";
import { brainsClient, promotionsClient, type BrainDestination, type BrainScope, type PublicationReview, type PromotionSuggestion, type Publication } from "../../brains/api/BrainsClient";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import MarkdownContent from "../../../components/content/MarkdownContent.vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage } from "../../../utils/errors";

const props = defineProps<{ noteId: string | null; dirty: boolean; sourceVersion?: string }>();
const destinations = ref<BrainDestination[]>([]);
const suggestions = ref<PromotionSuggestion[]>([]);
const publications = ref<Publication[]>([]);
const review = ref<PublicationReview | null>(null);
const scope = ref<BrainScope>("personal");
const draft = ref("");
const path = ref("");
const busy = ref(false);
const error = ref("");
const notice = ref("");
const audience = ref(false);
const consent = ref(false);
const requestKey = ref("");
let generation = 0;
let refreshGeneration = 0;
const dialogOpen = ref(false);
const initialDraft = ref("");
const initialPath = ref("");
const retained = new Map<string, { review: PublicationReview; draft: string; path: string; scope: BrainScope; initialDraft: string; initialPath: string; requestKey: string }>();
const edited = computed(() => !!review.value && (draft.value !== initialDraft.value || path.value !== initialPath.value));
const hasDrafts = computed(() => edited.value || [...retained.values()].some(item => item.draft !== item.initialDraft || item.path !== item.initialPath));
function retain(): void {
  if (review.value) retained.set(review.value.note_id, { review: review.value, draft: draft.value, path: path.value, scope: scope.value, initialDraft: initialDraft.value, initialPath: initialPath.value, requestKey: requestKey.value });
}
const discardOpen = ref(false);
let leaveAnswer: ((value: boolean) => void) | null = null;
function answerLeave(discard: boolean): void { discardOpen.value = false; leaveAnswer?.(discard); leaveAnswer = null; }
if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) onBeforeRouteLeave(() => {
  if (busy.value) return false;
  if (!hasDrafts.value) return true;
  discardOpen.value = true;
  return new Promise<boolean>(resolve => { leaveAnswer = resolve; });
});
function beforeUnload(event: BeforeUnloadEvent): void { if (hasDrafts.value) { event.preventDefault(); event.returnValue = ""; } }
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onUnmounted(() => { ++generation; ++refreshGeneration; window.removeEventListener("beforeunload", beforeUnload); });
const writable = computed(() => destinations.value.filter(d => d.writable));
const destination = computed(() => writable.value.find(d => d.scope === scope.value));
const notePublications = computed(() => publications.value.filter(p => p.note_id === props.noteId));
async function refresh() {
  const request = ++refreshGeneration;
  try { const result = await Promise.all([
    brainsClient.destinations(), promotionsClient.suggestions(), promotionsClient.list()]);
    if (request === refreshGeneration) [destinations.value, suggestions.value, publications.value] = result; }
  catch (e) { if (request === refreshGeneration) error.value = errorMessage(e); }
}
onMounted(refresh);
watch(() => [props.noteId, props.sourceVersion], () => { ++generation; retain(); review.value = null; dialogOpen.value = false; busy.value = false; error.value = ""; void refresh(); });
watch(scope, () => { audience.value = false; });
function newPath(title: string, folder: string) {
  const slug = title.replace(/[^\p{L}\p{N}_-]+/gu, "-").replace(/^-|-$/g, "").slice(0, 80) || "Note";
  return `${folder ? folder + "/" : ""}${slug}-${crypto.randomUUID().slice(0, 12)}.md`;
}
async function open(id: string, suggestion?: PromotionSuggestion) {
  if (busy.value) return;
  const request = ++generation;
  const sourceVersion = props.sourceVersion;
  const selectedNote = props.noteId;
  const ownsRequest = () => request === generation && selectedNote === props.noteId && sourceVersion === props.sourceVersion;
  if (review.value?.note_id !== id) { retain(); review.value = null; dialogOpen.value = false; }
  const previous = retained.get(id);
  if (review.value?.note_id === id) { dialogOpen.value = true; return; }
  busy.value = true; error.value = ""; audience.value = false;
  try {
    await refresh();
    if (!ownsRequest()) return;
    const note = await promotionsClient.review(id);
    if (!ownsRequest()) return;
    scope.value = previous?.scope ?? suggestion?.scope ?? writable.value[0]?.scope ?? "personal";
    if (!destination.value) throw new Error("Configure a writable brain destination before promoting a Note.");
    if (suggestion && (suggestion.source_hash !== note.source_hash || suggestion.source_revision !== note.source_revision || suggestion.generation !== destination.value.generation))
      throw new Error("The Note or destination changed. Request a new suggestion.");
    draft.value = suggestion?.draft ?? `# ${note.title}\n\n${note.body}`;
    path.value = newPath(suggestion?.title ?? note.title, suggestion?.folder ?? destination.value.folder);
    initialDraft.value = draft.value; initialPath.value = path.value;
    if (previous) {
      draft.value = previous.draft; path.value = previous.path;
      notice.value = "Your publication draft was retained. Review it against the latest saved Note before publishing.";
    }
    requestKey.value = crypto.randomUUID();
    review.value = note; dialogOpen.value = true;
  } catch (e) { if (ownsRequest()) error.value = errorMessage(e); }
  finally { if (ownsRequest()) busy.value = false; }
}
async function suggest(selected: boolean) {
  if (busy.value) return;
  const request = ++generation;
  busy.value = true; error.value = ""; consent.value = false;
  try {
    const ids = selected && props.noteId ? [props.noteId] : [];
    const result = await promotionsClient.suggest(ids, ids);
    if (request !== generation) return;
    suggestions.value = result;
    notice.value = suggestions.value.length ? "Review each suggestion before publishing." : "No new promotion suggestions.";
  } catch (e) { if (request === generation) error.value = errorMessage(e); }
  finally { if (request === generation) busy.value = false; }
}
async function reconcile(id: string) {
  if (busy.value) return;
  const request = ++generation;
  busy.value = true; error.value = "";
  try { await promotionsClient.reconcile(id); if (request !== generation) return; await refresh(); if (request !== generation) return; notice.value = "The reserved publication was reconciled."; }
  catch (e) { if (request === generation) error.value = errorMessage(e); }
  finally { if (request === generation) busy.value = false; }
}
async function dismiss(item: PromotionSuggestion) {
  if (busy.value) return;
  const request = ++generation;
  busy.value = true;
  try { await promotionsClient.dismiss(item.id); if (request !== generation) return; suggestions.value = suggestions.value.filter(s => s.id !== item.id); }
  catch (e) { if (request === generation) error.value = errorMessage(e); }
  finally { if (request === generation) busy.value = false; }
}
async function publish() {
  if (busy.value || !review.value || !destination.value || scope.value === "instance" && !audience.value) return;
  const request = ++generation;
  const noteId = review.value.note_id;
  busy.value = true; error.value = "";
  try {
    const result = await promotionsClient.publish(review.value.note_id, {
      source_hash: review.value.source_hash, source_revision: review.value.source_revision, scope: scope.value,
      destination_revision: destination.value.revision, generation: destination.value.generation!, path: path.value,
      draft: draft.value, idempotency_key: requestKey.value, shared_audience_reviewed: audience.value });
    if (request !== generation) return;
    notice.value = `Published ${result.path}. The original Note is preserved.`;
    retained.delete(noteId);
    review.value = null; dialogOpen.value = false;
    await refresh();
  } catch (e) { if (request === generation) error.value = errorMessage(e); }
  finally { if (request === generation) busy.value = false; }
}
</script>
<template>
  <section class="note-promotions" aria-label="Obsidian promotion" :aria-busy="busy">
    <div class="actions">
      <button v-if="writable.length" type="button" :disabled="busy || dirty || !noteId" @click="noteId && open(noteId)">Promote to Obsidian</button>
      <button type="button" :disabled="busy || !writable.length" @click="suggest(false)">Suggest promotions</button>
      <button type="button" :disabled="busy || dirty || !noteId || !writable.length" @click="consent = true">Ask AI about this Note</button>
    </div>
    <p class="muted">AI reviews only Notes shared with agents unless you explicitly select a private Note. Each batch allows 20 Notes and 40,000 characters.</p>
    <p v-if="dirty" class="muted">Save your Note before reviewing a publication.</p>
    <p v-if="error && !review" class="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <p v-for="item in notePublications" :key="item.id"><a :href="`/brains?scope=${item.scope}&path=${encodeURIComponent(item.path)}`">{{ item.scope }}: {{ item.path }}</a> · {{ item.status }}{{ item.source_changed ? " · Note changed since publication" : "" }} <button v-if="item.status === 'pending'" type="button" :disabled="busy" @click="reconcile(item.id)">Reconcile publication</button></p>
    <article v-for="item in suggestions" :key="item.id"><h4>{{ item.title }}</h4><p>{{ item.reason }}</p><p>{{ item.scope }} · {{ item.folder }} · {{ item.tags.join(", ") }}</p>
      <button type="button" :disabled="busy" @click="open(item.note_id, item)">Review suggestion</button>
      <button type="button" :disabled="busy" @click="dismiss(item)">Dismiss</button>
    </article>
    <ConfirmModal :open="consent" title="Send this Note for AI review?" message="This sends the selected Note, including a private Note, to the configured AI provider. It does not change the Note agent-access switch." confirm-label="Send for review" @close="consent = false" @confirm="suggest(true)">
      <p>This explicitly sends the selected Note, including a private Note, to the configured AI provider. It does not change the Note's agent-access switch.</p>
    </ConfirmModal>
    <ConfirmModal :open="discardOpen" title="Discard publication drafts?" message="Edited publication drafts will be lost when you leave." confirm-label="Discard drafts" @confirm="answerLeave(true)" @close="answerLeave(false)" />
    <BaseModal v-if="review" :open="dialogOpen" title="Review Obsidian publication" wide @close="!busy && (dialogOpen = false)">
      <fieldset :disabled="busy">
        <label>Destination<select v-model="scope" aria-label="Destination"><option v-for="d in writable" :key="d.scope" :value="d.scope">{{ d.label }} · {{ d.scope }}</option></select></label>
        <p v-if="scope === 'instance'">Audience: every signed-in user can read this document.</p><p v-else>Audience: only your account.</p>
        <ToggleSwitch v-if="scope === 'instance'" :checked="audience" @change="audience = ($event.target as HTMLInputElement).checked">I reviewed the shared audience</ToggleSwitch>
        <label>New document path<input v-model="path" maxlength="500" /></label>
        <label>Publication Markdown<textarea v-model="draft" rows="10" maxlength="40000" /></label>
        <h4>Preview</h4><MarkdownContent :text="draft" />
        <p>The original Note stays intact. This creates a separate document; later edits do not synchronize.</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="button" :disabled="!draft || !path || scope === 'instance' && !audience" @click="publish">{{ busy ? "Publishing…" : "Publish document" }}</button>
      </fieldset>
    </BaseModal>
  </section>
</template>
<style scoped>
.note-promotions { padding: 12px 0; border-bottom: 1px solid var(--border); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
fieldset, label { display: grid; gap: 8px; border: 0; min-width: 0; padding: 0; }
input, select, textarea { box-sizing: border-box; width: 100%; padding: 8px; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius-md); }
button { padding: 7px 12px; border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--surface); color: var(--text); cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
article { margin-top: 12px; border-top: 1px solid var(--border); }
.muted { color: var(--muted); font-size: .9em; }
.error { color: var(--danger); }
</style>
