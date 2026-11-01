<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { matchesWords } from "../../utils/search";
import PageLayout from "../../components/layout/PageLayout.vue";
import ListEditorLayout from "../../components/layout/ListEditorLayout.vue";
import ListRow from "../../components/ui/lists/ListRow.vue";
import SearchField from "../../components/ui/lists/SearchField.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import DangerZone from "../../components/ui/status/DangerZone.vue";
import CharacterCount from "../../components/ui/status/CharacterCount.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import { useDeleteConfirm } from "../../composables/useDeleteConfirm";
import { useListLoad } from "../../composables/useListLoad";
import { useUnsavedGuard } from "../../composables/useUnsavedGuard";
import { growOnResize, growToContent } from "../../utils/browser/autoGrow";
import "../../components/layout/infoPage.css";
import { errorMessage } from "../../utils/errors";
import { SKILL_LIMITS, skillsClient, type Skill, type SkillStatus, type SkillText } from "./api/SkillsClient";

const { items: skills, loading, loadError, load } = useListLoad(() => skillsClient.list());
const notice = ref("");
const actionError = ref("");
const busyId = ref<number | null>(null);
const query = ref("");
const matches = computed(() => skills.value.filter((skill) => matchesWords(query.value, skill.title, skill.when_to_use)));
const groups = computed(() => [
  { status: "proposed" as const, title: "Waiting for approval", hint: "Ember proposed these. Nothing here is used until you approve it.", items: matches.value.filter((s) => s.status === "proposed") },
  { status: "active" as const, title: "Active", hint: "Ember may follow these when a task matches.", items: matches.value.filter((s) => s.status === "active") },
  { status: "retired" as const, title: "Retired", hint: "Never used. Delete them or send them back for review.", items: matches.value.filter((s) => s.status === "retired") },
]);

async function move(skill: Skill, status: SkillStatus, done: string): Promise<void> {
  if (busy.value) return;
  busyId.value = skill.id;
  actionError.value = "";
  notice.value = "";
  try {
    const updated = await skillsClient.setStatus(skill.id, status);
    skills.value = skills.value.map((s) => (s.id === updated.id ? updated : s));
    // A status change does not replace an in-progress text draft.
    if (editing.value?.id === updated.id) editing.value = updated;
    notice.value = done;
  } catch (error) { actionError.value = errorMessage(error); }
  finally { busyId.value = null; }
}

const { deleting, removing, removeError, ask: askDelete, confirm: remove } = useDeleteConfirm<Skill>(
  (skill) => skillsClient.remove(skill.id),
  (skill) => {
    skills.value = skills.value.filter((s) => s.id !== skill.id);
    if (editing.value?.id === skill.id) showEditor(null);
    notice.value = "Skill deleted.";
  },
  () => busy.value,
);

const editing = ref<Skill | null>(null);
const listScroll = ref<HTMLElement | null>(null);
const searchField = ref<InstanceType<typeof SearchField> | null>(null);
const draft = ref<SkillText>({ title: "", when_to_use: "", steps: "", tools: "" });
const saving = ref(false);
const editError = ref("");
const busy = computed((): boolean => saving.value || removing.value || busyId.value !== null);
const filled = computed(() => draft.value.title.trim() !== "" && draft.value.when_to_use.trim() !== "" && draft.value.steps.trim() !== "");
const dirty = computed(() => editing.value !== null && (Object.keys(draft.value) as (keyof SkillText)[]).some((key) => draft.value[key] !== editing.value![key]));
const discardTarget = ref<Skill | null>(null);
const guard = useUnsavedGuard({
  dirty: () => dirty.value,
  busy: () => busy.value,
  onAsk: () => { discardTarget.value = null; },
});
const discardOpen = guard.open;
function showEditor(skill: Skill | null): void {
  const previousId = editing.value?.id;
  editing.value = skill;
  if (skill) draft.value = { title: skill.title, when_to_use: skill.when_to_use, steps: skill.steps, tools: skill.tools };
  editError.value = "";
  void nextTick(async () => {
    // Let any discard/delete dialog finish closing before moving focus.
    await nextTick();
    if (editing.value?.id !== skill?.id) return;
    if (skill) titleField.value?.focus();
    else {
      const row = listScroll.value?.querySelector<HTMLButtonElement>(`button[data-skill-id="${previousId}"]`);
      if (row) row.focus();
      else searchField.value?.$el.querySelector("input")?.focus();
    }
  });
}
function askEdit(skill: Skill | null): void {
  if (busy.value || (skill !== null && skill.id === editing.value?.id)) return;
  if (dirty.value) { discardTarget.value = skill; discardOpen.value = true; }
  else showEditor(skill);
}
function answerDiscard(discard: boolean): void {
  if (discard) showEditor(discardTarget.value);
  discardTarget.value = null;
  guard.answer(discard);
}
const titleField = ref<HTMLTextAreaElement | null>(null);
growOnResize(titleField);
watch([() => draft.value.title, () => editing.value?.id], async () => {
  await nextTick();
  if (titleField.value) growToContent(titleField.value);
});
async function saveEdit(): Promise<void> {
  if (!editing.value || busy.value || !filled.value) return;
  saving.value = true;
  editError.value = "";
  try {
    const updated = await skillsClient.update(editing.value.id, draft.value);
    skills.value = skills.value.map((s) => (s.id === updated.id ? updated : s));
    showEditor(null);
    notice.value = "Skill saved. Its worked and failed counts started over.";
  } catch (error) { editError.value = errorMessage(error); }
  finally { saving.value = false; }
}
</script>

<template>
  <PageLayout title="Skills" class="skills info-content" :class="{ 'skill-open': editing !== null }" wide fill description="How-tos Ember proposed after solving a task. Nothing is used until you approve it.">
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="actionError" class="error action-error" role="alert">{{ actionError }}</p>
    <StateMessage v-if="loading" kind="loading">Loading skills…</StateMessage>
    <StateMessage v-else-if="loadError" kind="error" @retry="load">Could not load skills: {{ loadError }}</StateMessage>
    <StateMessage v-else-if="skills.length === 0" kind="empty" title="No skills yet.">When Ember solves a multi-step task it may propose a skill here for you to approve.</StateMessage>
    <ListEditorLayout v-else class="skills-layout" :editing="editing !== null" list-label="Skill list" editor-label="Skill editor" back-label="All skills" :busy="busy" :saving="saving" :dirty="dirty" :can-save="!busy && filled" visible-scrollbars @back="askEdit(null)" @submit="saveEdit">
      <template #list>
        <div class="list-heading"><span>All skills</span><span>{{ skills.length }}</span></div>
        <SearchField ref="searchField" v-model="query" class="skills-search" label="Search skills" placeholder="Search skills…" />
        <div ref="listScroll" class="list-scroll pane-scroll">
          <section v-for="group in groups" v-show="group.items.length" :key="group.status" class="skill-group" :aria-label="group.title">
            <header class="group-heading">
              <h3>{{ group.title }} <span class="group-count">{{ group.items.length }}</span></h3>
              <p v-if="group.status === 'proposed'">{{ group.hint }}</p>
              <span v-else class="sr-only">{{ group.hint }}</span>
            </header>
            <article v-for="skill in group.items" :key="skill.id" class="skill-item" :aria-label="skill.title">
              <ListRow class="skill-row" :active="editing?.id === skill.id" :data-skill-id="skill.id" :aria-label="'Edit skill ' + skill.title" :disabled="busy" @click="askEdit(skill)">
                <span class="row-title">{{ skill.title }}<span v-if="skill.failing" class="status-badge">⚠ Often fails</span></span>
                <span class="row-description">{{ skill.when_to_use }}</span>
                <span v-if="skill.status === 'active'" class="row-meta">Worked {{ skill.successes }}×, failed {{ skill.failures }}×</span>
                <template v-if="skill.status === 'proposed'" #actions>
                  <button type="button" class="pill-btn primary" :disabled="busy" :aria-busy="busyId === skill.id" @click="move(skill, 'active', 'Skill approved.')">Approve</button>
                </template>
              </ListRow>
            </article>
          </section>
          <StateMessage v-if="matches.length === 0" kind="empty" title="No skills match your search.">Try a different word or clear your search.</StateMessage>
        </div>
        <p class="list-help">Only approved skills are offered to Ember.</p>
      </template>
      <template #head>
        <span class="editor-context">Edit skill</span>
        <span class="status-badge">{{ editing?.status === 'proposed' ? 'Waiting for approval' : editing?.status === 'active' ? 'Active' : 'Retired' }}</span>
      </template>
      <template #editor>
        <div v-if="editing" :key="editing.id" class="writing">
          <label class="title-field" for="skill-title"><span class="sr-only">Title</span><textarea id="skill-title" ref="titleField" v-model="draft.title" rows="1" aria-label="Title" aria-describedby="skill-title-count" :maxlength="SKILL_LIMITS.title" :disabled="busy" /><CharacterCount id="skill-title-count" :length="draft.title.length" :max="SKILL_LIMITS.title" /></label>
          <label class="document-field" for="skill-when"><span id="skill-when-label" class="field-label">When to use</span><textarea id="skill-when" aria-labelledby="skill-when-label" v-model="draft.when_to_use" rows="2" aria-describedby="skill-when-count" :maxlength="SKILL_LIMITS.when_to_use" :disabled="busy" /><CharacterCount id="skill-when-count" :length="draft.when_to_use.length" :max="SKILL_LIMITS.when_to_use" /></label>
          <label class="document-field steps-field" for="skill-steps"><span id="skill-steps-label" class="field-label">Steps</span><textarea id="skill-steps" aria-labelledby="skill-steps-label" v-model="draft.steps" rows="5" aria-describedby="skill-steps-count" :maxlength="SKILL_LIMITS.steps" :disabled="busy" /><CharacterCount id="skill-steps-count" :length="draft.steps.length" :max="SKILL_LIMITS.steps" /></label>
          <p class="writing-note">Saving starts the worked and failed counts over. Keep the steps generic: no names, secrets or personal details.</p>
          <p v-if="editing.failing" class="failing-note">Ember is no longer offered this skill. Edit it to try again, or retire it.</p>
          <div class="secondary-tools">
            <details>
              <summary>Tools <span>{{ draft.tools || 'None' }} <span aria-hidden="true">›</span></span></summary>
              <label class="tools-field" for="skill-tools"><span id="skill-tools-label" class="field-label">Tools (optional, comma-separated)</span><input id="skill-tools" aria-labelledby="skill-tools-label" v-model="draft.tools" type="text" aria-describedby="skill-tools-count" :maxlength="SKILL_LIMITS.tools" :disabled="busy" /><CharacterCount id="skill-tools-count" :length="draft.tools.length" :max="SKILL_LIMITS.tools" /></label>
            </details>
            <details>
              <summary>Manage skill <span aria-hidden="true">›</span></summary>
              <div class="manage-actions">
                <button v-if="editing.status === 'proposed'" type="button" class="link-btn danger" :disabled="busy" :aria-busy="busyId === editing.id" @click="move(editing, 'retired', 'Skill rejected.')">Reject</button>
                <button v-if="editing.status === 'active'" type="button" class="link-btn" :disabled="busy" :aria-busy="busyId === editing.id" @click="move(editing, 'retired', 'Skill retired.')">Retire</button>
                <button v-if="editing.status === 'retired'" type="button" class="link-btn" :disabled="busy" :aria-busy="busyId === editing.id" @click="move(editing, 'proposed', 'Skill sent back for review.')">Send back for review</button>
              </div>
              <DangerZone label="Danger zone"><button type="button" class="danger" :aria-label="'Delete skill ' + editing.title" :disabled="busy" @click="askDelete(editing)">Delete skill</button></DangerZone>
            </details>
          </div>
          <p v-if="editError" class="error" role="alert">{{ editError }}</p>
        </div>
      </template>
      <template #actions><button type="button" class="pill-btn ghost" :disabled="busy" @click="askEdit(null)">Cancel</button></template>
      <template #placeholder><StateMessage kind="empty" title="Review a skill">Choose a skill to read its steps or edit it. Approve the ones you want Ember to use.</StateMessage></template>
    </ListEditorLayout>
    <ConfirmModal :open="deleting !== null" title="Delete this skill?" :message="removeError || 'Ember will no longer know it. This cannot be undone.'" confirm-label="Delete skill" danger :busy="removing" @confirm="remove" @close="!removing && (deleting = null)" />
    <ConfirmModal :open="discardOpen" title="Discard your changes?" message="This skill has changes you have not saved." confirm-label="Discard" danger @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
.skills-layout { --workspace-columns: 360px minmax(0, 1fr); }
.skills-search { margin-bottom: 12px; flex-shrink: 0; }
.list-scroll { flex: 1; min-height: 0; }
.skill-group { margin-bottom: 24px; }
.group-heading { padding: 0 10px 12px; }
.group-heading h3 { font-size: .9em; font-weight: 600; }
.group-heading p { margin: 4px 0 0; color: var(--muted); font-size: .8em; }
.group-count { color: var(--muted); margin-left: 6px; font-weight: 400; }
.skill-item { margin-bottom: 6px; border-bottom: 1px solid var(--border); }
.row-title { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-weight: 500; line-height: 1.6; overflow-wrap: anywhere; }
.row-description { color: var(--muted); line-height: 1.6; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.row-meta { color: var(--muted); font-size: .85em; }
.list-help { color: var(--muted); font-size: .7em; margin: 14px 10px 0; padding-top: 14px; border-top: 1px solid var(--border); flex-shrink: 0; }
.editor-context { font-size: .8em; color: var(--muted); margin-right: auto; }
.writing { display: flex; flex-direction: column; flex: 1 0 auto; gap: 18px; padding: 30px 36px 20px; }
.title-field, .document-field, .tools-field { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.field-label { font-size: .8em; color: var(--muted); font-weight: 500; }
.writing textarea { width: 100%; min-width: 0; padding: 0; border: 0; border-radius: var(--radius-sm); color: var(--text); background: transparent; font: inherit; line-height: 1.9; resize: vertical; }
.writing .title-field textarea { font-size: 1.6em; font-weight: 600; letter-spacing: -.025em; line-height: 1.4; resize: none; overflow-y: hidden; }
.writing :deep(.character-count) { align-self: flex-end; }
.steps-field textarea { min-height: 180px; }
.writing-note { font-size: .8em; color: var(--muted); margin: 0; line-height: 1.6; }
.failing-note { color: var(--danger); font-size: .85em; margin: 0; }
.secondary-tools { margin-top: 6px; }
.secondary-tools details { border-top: 1px solid var(--border); }
summary { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 0; font-size: .85em; cursor: pointer; list-style: none; overflow-wrap: anywhere; }
summary::-webkit-details-marker { display: none; }
summary > span { color: var(--muted); font-size: .9em; min-width: 0; text-align: right; }
summary > span > span { margin-left: 12px; }
.secondary-tools details[open] > summary { color: var(--accent); }
.tools-field { margin-bottom: 16px; }
.manage-actions { padding-bottom: 12px; }
.secondary-tools :deep(.danger-panel) { margin-bottom: 16px; }
.action-error { margin: 0 0 12px; font-size: .85em; }
@media (min-width: 1200px) { .writing { padding-inline: max(36px, calc((100% - 760px) / 2)); } }
@media (max-width: 900px) and (min-width: 768px) {
  .skills .skills-layout { --workspace-columns: 280px minmax(0, 1fr); }
  .writing { padding-inline: 22px; }
}
@media (max-width: 767px) {
  .skills :deep(.page-column) { padding: 18px 16px 12px; }
  .skills :deep(.page-head) { margin-bottom: 16px; }
  .skills :deep(.page-title) { margin: 0; }
  .skills :deep(.page-description) { display: none; }
  .skills.skill-open :deep(.page-head) { display: none; }
  .writing { padding: 24px 20px 18px; }
  .writing .title-field textarea { font-size: 1.45em; }
  .steps-field textarea { min-height: 230px; }
  .skill-item button, .secondary-tools button, summary { min-width: 44px; min-height: 44px; }
}
</style>
