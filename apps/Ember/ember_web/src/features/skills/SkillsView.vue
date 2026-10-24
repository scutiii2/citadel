<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import { errorMessage } from "../../utils/errors";
import { skillsClient, type Skill, type SkillStatus } from "./api/SkillsClient";

const skills = ref<Skill[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");
const actionError = ref("");
const busyId = ref<number | null>(null);

const groups = computed(() => [
  { status: "proposed" as const, title: "Waiting for approval", hint: "Ember proposed these. Nothing here is used until you approve it.", items: skills.value.filter((s) => s.status === "proposed") },
  { status: "active" as const, title: "Active", hint: "Ember may follow these when a task matches.", items: skills.value.filter((s) => s.status === "active") },
  { status: "retired" as const, title: "Retired", hint: "Never used. Delete them or send them back for review.", items: skills.value.filter((s) => s.status === "retired") },
]);

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try { skills.value = await skillsClient.list(); }
  catch (error) { loadError.value = errorMessage(error); }
  finally { loading.value = false; }
}
onMounted(load);

async function move(skill: Skill, status: SkillStatus, done: string): Promise<void> {
  if (busyId.value !== null) return;
  busyId.value = skill.id;
  actionError.value = "";
  notice.value = "";
  try {
    const updated = await skillsClient.setStatus(skill.id, status);
    skills.value = skills.value.map((s) => (s.id === updated.id ? updated : s));
    notice.value = done;
  } catch (error) { actionError.value = errorMessage(error); }
  finally { busyId.value = null; }
}

const deleting = ref<Skill | null>(null);
const removing = ref(false);
const removeError = ref("");
function askDelete(skill: Skill): void { deleting.value = skill; removeError.value = ""; }
async function remove(): Promise<void> {
  if (!deleting.value || removing.value) return;
  removing.value = true;
  removeError.value = "";
  try {
    await skillsClient.remove(deleting.value.id);
    const gone = deleting.value.id;
    skills.value = skills.value.filter((s) => s.id !== gone);
    deleting.value = null;
    notice.value = "Skill deleted.";
  } catch (error) { removeError.value = errorMessage(error); }
  finally { removing.value = false; }
}

/** Three or more failures that outnumber the successes: worth a second look. */
const oftenFails = (skill: Skill): boolean => skill.failures >= 3 && skill.failures > skill.successes;
</script>

<template>
  <PageLayout title="Skills" description="How-tos Ember proposed after solving a task. Nothing is used until you approve it.">
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
    <p v-if="loading" class="muted" role="status">Loading skills…</p>
    <div v-else-if="loadError" class="error" role="alert"><p>Could not load skills: {{ loadError }}</p><button type="button" class="chip" @click="load">Try again</button></div>
    <div v-else-if="skills.length === 0" class="empty"><h3>No skills yet.</h3><p>When Ember solves a multi-step task it may propose a skill here for you to approve.</p></div>
    <template v-else>
      <section v-for="group in groups" v-show="group.items.length" :key="group.status" class="group" :aria-label="group.title">
        <header><h2>{{ group.title }} <span class="count">{{ group.items.length }}</span></h2><p class="muted">{{ group.hint }}</p></header>
        <article v-for="skill in group.items" :key="skill.id" class="skill" :aria-label="skill.title">
          <h3>{{ skill.title }}<span v-if="oftenFails(skill)" class="badge">Often fails</span></h3>
          <p class="when"><b>When to use:</b> {{ skill.when_to_use }}</p>
          <p class="steps">{{ skill.steps }}</p>
          <p v-if="skill.tools" class="muted tools">Tools: {{ skill.tools }}</p>
          <p v-if="skill.status === 'active'" class="muted">Worked {{ skill.successes }}×, failed {{ skill.failures }}×</p>
          <div class="actions">
            <button v-if="skill.status === 'proposed'" type="button" class="primary" :disabled="busyId !== null" @click="move(skill, 'active', 'Skill approved.')">Approve</button>
            <button v-if="skill.status === 'proposed'" type="button" class="chip" :disabled="busyId !== null" @click="move(skill, 'retired', 'Skill rejected.')">Reject</button>
            <button v-if="skill.status === 'active'" type="button" class="chip" :disabled="busyId !== null" @click="move(skill, 'retired', 'Skill retired.')">Retire</button>
            <button v-if="skill.status === 'retired'" type="button" class="chip" :disabled="busyId !== null" @click="move(skill, 'proposed', 'Skill sent back for review.')">Send back for review</button>
            <button type="button" class="danger" :aria-label="'Delete skill ' + skill.title" :disabled="busyId !== null" @click="askDelete(skill)">Delete</button>
          </div>
        </article>
      </section>
    </template>
    <ConfirmModal :open="deleting !== null" title="Delete this skill?" :message="removeError || 'Ember will no longer know it. This cannot be undone.'" confirm-label="Delete skill" danger :busy="removing" @confirm="remove" @close="!removing && (deleting = null)" />
  </PageLayout>
</template>

<style scoped>
.notice { margin: 0 0 12px; color: var(--muted); font-size: .85em; }
.group { margin-bottom: 28px; }
.group h2 { font-size: 1em; font-weight: 600; margin: 0 0 4px; }
.count { color: var(--muted); font-weight: 400; margin-left: 4px; }
.group header p { margin: 0 0 12px; font-size: .8em; }
.skill { padding: 16px; margin-bottom: 10px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.skill h3 { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 0 8px; font-size: 1em; }
.skill p { margin: 0 0 8px; overflow-wrap: anywhere; }
.steps { white-space: pre-wrap; line-height: 1.6; }
.tools, .when { font-size: .85em; }
.badge { padding: 2px 8px; font-size: .7em; font-weight: 500; color: var(--danger); border: 1px solid var(--danger); border-radius: var(--radius-full); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.primary, .chip, .danger { font: inherit; font-size: .85em; padding: 8px 14px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-full); cursor: pointer; }
.primary { background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); font-weight: 600; }
.danger { color: var(--danger); border-color: var(--danger); margin-left: auto; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.empty { padding: 20px 4px; color: var(--muted); }
.empty h3 { font-size: 1em; font-weight: 500; margin: 0 0 8px; color: var(--text); }
.muted { color: var(--muted); }
.error { color: var(--danger); }
@media (max-width: 767px) { .actions button { min-height: 44px; } }
</style>
