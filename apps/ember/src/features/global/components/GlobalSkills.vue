<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { RecordDrawer } from "@citadel/ui";
import { ConfirmModal } from "@citadel/ui";
import SearchField from "../../../components/ui/lists/SearchField.vue";
import CharacterCount from "../../../components/ui/status/CharacterCount.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { matchesWords } from "../../../utils/search";
import { SKILL_LIMITS, type Skill, type SkillStatus, type SkillText } from "../../skills/api/SkillsClient";
import { globalClient } from "../api/GlobalClient";

const props = defineProps<{ canWrite: boolean }>();
const auth = useAuthStore();
const skills = ref<Skill[]>([]);
const query = ref("");
const loading = ref(false);
const loadError = ref("");
const actionError = ref("");
const notice = ref("");
const busy = ref(false);
const editing = ref<Skill | null>(null);
const deleting = ref<Skill | null>(null);
const draft = ref<SkillText>({ title: "", when_to_use: "", steps: "", tools: "" });
let run = 0;

const groups = [
  { status: "proposed", title: "Waiting for approval", hint: "Agents can use these after approval." },
  { status: "active", title: "Active", hint: "Agents may follow these when a task matches." },
  { status: "retired", title: "Retired", hint: "Agents cannot use these. Delete them or send them back for review." },
] as const;
const transitions = {
  proposed: { next: "active", label: "Approve", done: "Skill approved." },
  active: { next: "retired", label: "Retire", done: "Skill retired." },
  retired: { next: "proposed", label: "Send back for review", done: "Skill sent back for review." },
} as const satisfies Record<SkillStatus, { next: SkillStatus; label: string; done: string }>;
const fields = [
  { key: "title", label: "Title", required: true },
  { key: "when_to_use", label: "When to use", required: true },
  { key: "steps", label: "Steps", required: true },
  { key: "tools", label: "Tools", required: false },
] as const;
const matches = computed(() => skills.value.filter((s) => matchesWords(query.value, s.title, s.when_to_use, s.steps, s.tools)));
const sections = computed(() => (props.canWrite ? groups : [{ ...groups[1], title: "Active skills" }]).map((g) => ({
  ...g, items: matches.value.filter((s) => s.status === g.status),
})));

function fieldProblem(field: typeof fields[number]): string {
  const value = draft.value[field.key];
  const limit = SKILL_LIMITS[field.key];
  if (value.length > limit) return `${field.label} must be ${limit} characters or fewer.`;
  if (field.required && !value.trim()) return `${field.label} is required.`;
  return "";
}

const canSave = computed(() => {
  const skill = editing.value;
  return props.canWrite && !busy.value && skill && !fields.some(fieldProblem) &&
    fields.some(({ key }) => draft.value[key] !== skill[key]);
});

function edit(skill: Skill | null): void {
  editing.value = skill;
  draft.value = { title: skill?.title ?? "", when_to_use: skill?.when_to_use ?? "", steps: skill?.steps ?? "", tools: skill?.tools ?? "" };
  actionError.value = "";
}

function clear(): void {
  run++;
  skills.value = [];
  query.value = notice.value = loadError.value = "";
  editing.value = deleting.value = null;
  edit(null);
  busy.value = loading.value = false;
}

async function load(): Promise<void> {
  if (!auth.account) return;
  const current = ++run;
  loading.value = true;
  loadError.value = "";
  try {
    const items = await (props.canWrite ? globalClient.allSkills() : globalClient.skills());
    if (current === run) skills.value = items;
  } catch (err) {
    if (current === run) loadError.value = errorMessage(err);
  } finally {
    if (current === run) loading.value = false;
  }
}

watch(() => auth.account?.id, clear, { flush: "sync" });
watch(() => props.canWrite, () => { clear(); void load(); }, { immediate: true });
onBeforeUnmount(clear);

function replace(skill: Skill): void {
  skills.value = skills.value.map((row) => row.id === skill.id ? skill : row);
}

async function act<T>(work: () => Promise<T>, apply: (result: T) => void, message: string): Promise<void> {
  if (!auth.account || !props.canWrite || busy.value) return;
  const current = run;
  busy.value = true;
  notice.value = actionError.value = "";
  try {
    const result = await work();
    if (run !== current) return;
    apply(result);
    notice.value = message;
  } catch (err) {
    if (run === current) {
      deleting.value = null;
      actionError.value = errorMessage(err);
    }
  } finally {
    if (run === current) busy.value = false;
  }
}

function move(skill: Skill): void {
  const { next, done } = transitions[skill.status];
  void act(() => globalClient.setSkillStatus(skill.id, next), replace, done);
}

function save(): void {
  const skill = editing.value;
  if (!skill || !canSave.value) return;
  const text = { ...draft.value, title: draft.value.title.trim(), when_to_use: draft.value.when_to_use.trim(), steps: draft.value.steps.trim(), tools: draft.value.tools.trim() };
  void act(() => globalClient.updateSkill(skill.id, text), (updated) => {
    replace(updated);
    edit(null);
  }, "Skill saved. Its worked and failed counts started over.");
}

function remove(): void {
  const skill = deleting.value;
  if (!skill) return;
  void act(() => globalClient.removeSkill(skill.id), () => {
    skills.value = skills.value.filter((row) => row.id !== skill.id);
    deleting.value = null;
  }, "Skill deleted.");
}
</script>

<template>
  <div class="global-skills">
    <SearchField v-model="query" class="search" label="Search global skills" />
    <p v-if="notice" class="feedback" role="status"><span aria-hidden="true">✓</span> {{ notice }}</p>
    <p v-if="actionError && !editing" class="feedback" role="alert"><span class="warning" aria-hidden="true">⚠</span> {{ actionError }}</p>
    <StateMessage v-if="loading" kind="loading">Loading skills…</StateMessage>
    <StateMessage v-else-if="loadError" class="load-state" kind="error" @retry="load"><span class="warning" aria-hidden="true">⚠</span> Could not load skills. {{ loadError }}</StateMessage>
    <template v-else>
      <StateMessage v-if="!matches.length" kind="empty">{{ query.trim() ? "No skills match your search." : "No skills yet." }}</StateMessage>
      <section v-for="section in sections" :key="section.status" :aria-label="section.title">
        <h3>{{ section.title }}</h3>
        <p class="hint">{{ section.hint }}</p>
        <article v-for="skill in section.items" :key="skill.id" class="skill" :aria-label="skill.title">
          <details>
            <summary><strong>{{ skill.title }}</strong></summary>
            <pre>{{ skill.steps }}</pre>
            <template v-if="skill.tools"><h4>Tools</h4><pre>{{ skill.tools }}</pre></template>
          </details>
          <p>{{ skill.when_to_use }}</p>
          <p v-if="skill.failing" class="feedback" role="note">
            <span class="warning" aria-hidden="true">⚠</span> Failing: agents are not offered it. Editing resets the counts.
          </p>
          <div v-if="canWrite" class="buttons">
            <button type="button" class="pill-btn ghost" :disabled="busy" @click="move(skill)">{{ transitions[skill.status].label }}</button>
            <button type="button" class="pill-btn ghost" :disabled="busy" @click="edit(skill)">Edit</button>
            <button type="button" class="pill-btn ghost" :disabled="busy" @click="deleting = skill">Delete</button>
          </div>
        </article>
      </section>
    </template>
    <RecordDrawer v-if="canWrite && editing" :open="true" title="Edit global skill" @close="!busy && edit(null)">
      <form class="dialog-form" @submit.prevent="save">
        <div v-for="field in fields" :key="field.key" class="field">
          <label :for="'global-skill-' + field.key">{{ field.label }}</label>
          <input v-if="field.key === 'title'" v-model="draft[field.key]" type="text"
            :id="'global-skill-' + field.key" :aria-label="field.label" :maxlength="SKILL_LIMITS[field.key]"
            :disabled="busy" :required="field.required" :aria-invalid="!!fieldProblem(field)"
            :aria-describedby="'global-skill-count-' + field.key + (fieldProblem(field) ? ' global-skill-error-' + field.key : '')" />
          <textarea v-else v-model="draft[field.key]"
            :id="'global-skill-' + field.key" :aria-label="field.label" :maxlength="SKILL_LIMITS[field.key]"
            :disabled="busy" :required="field.required" :aria-invalid="!!fieldProblem(field)"
            :aria-describedby="'global-skill-count-' + field.key + (fieldProblem(field) ? ' global-skill-error-' + field.key : '')" />
          <CharacterCount :id="'global-skill-count-' + field.key" :length="draft[field.key].length" :max="SKILL_LIMITS[field.key]" />
          <p v-if="fieldProblem(field)" :id="'global-skill-error-' + field.key" class="feedback" role="alert">
            <span class="warning" aria-hidden="true">⚠</span> {{ fieldProblem(field) }}
          </p>
        </div>
        <p v-if="actionError" class="feedback" role="alert"><span class="warning" aria-hidden="true">⚠</span> {{ actionError }}</p>
        <div class="buttons">
          <button type="button" class="pill-btn ghost" :disabled="busy" @click="edit(null)">Close</button>
          <button type="submit" class="pill-btn primary" :disabled="!canSave" :aria-busy="busy" @click.prevent="save">Save</button>
        </div>
      </form>
    </RecordDrawer>
    <ConfirmModal v-if="canWrite && deleting" :open="true" title="Delete global skill?" message="This removes the skill for everyone."
      danger confirm-label="Delete" :busy="busy" @close="!busy && (deleting = null)" @confirm="remove" />
  </div>
</template>

<style scoped>
.global-skills { display: grid; gap: 12px; min-width: 0; overflow-wrap: anywhere; }
h3, h4, p { margin: 0; }
.hint { color: var(--muted); font-size: .85em; margin: 4px 0 8px; }
.skill { display: grid; gap: 8px; padding: 8px 12px 12px; border-top: 1px solid var(--border); }
summary { min-height: 44px; align-content: center; cursor: pointer; }
pre { margin: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--code-bg); font: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }
.field { display: grid; gap: 4px; }
.field label { font-size: .85em; color: var(--muted); }
.field :is(input, textarea) { min-height: 44px; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.dialog-form .buttons { justify-content: flex-end; }
.buttons button, .search, .load-state :deep(button) { min-height: 44px; }
.feedback, .global-skills .load-state { color: var(--text); }
.warning { color: var(--warning); }
@media (max-width: 767px) {
  .field :is(input, textarea) { font-size: max(1em, 16px); }
}
</style>
