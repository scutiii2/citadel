<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, ref, watch } from "vue";
import { agentsAdminClient, type SharedPrompts } from "../../api/AgentsAdminClient";
import { errorMessage } from "../../utils/errors";
import { ConfirmModal } from "@citadel/ui";
import { RecordDrawer } from "@citadel/ui";

/** The prompt text every agent shares. Each text shows the built-in default
 * it falls back to; a text that differs has a dot and its own reset. Saving
 * restarts every agent (each builds its prompt once, at start), so it asks
 * first. The parent keeps `open`; `saved` fires after a successful save. */
const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; saved: [] }>();

interface PromptField {
  key: string;
  label: string;
  help: string;
  rows: number;
}

const FIELDS: PromptField[] = [
  { key: "app_name", label: "Assistant name", help: "The name every agent answers to.", rows: 1 },
  { key: "app_description", label: "Assistant description", help: "One line about what the assistant is.", rows: 2 },
  { key: "identity_template", label: "Identity line", help: "Opens every system prompt. Placeholders: {app_name}, {app_description}, {role}. An agent's own Identity field replaces it.", rows: 4 },
  { key: "default_instructions", label: "Default instructions", help: "Used by every agent whose own Instructions field is empty.", rows: 5 },
  { key: "roster_intro", label: "Specialist list intro", help: "Introduces the list of specialists an orchestrator can hand work to.", rows: 3 },
  { key: "caveman_instructions", label: "Caveman mode", help: "Added to the prompt when a chat turns caveman mode on.", rows: 6 },
];

const loaded = ref<SharedPrompts | null>(null);
const draft = ref<Record<string, string>>({});
const loading = ref(false);
const saving = ref(false);
const confirming = ref(false);
const discarding = ref(false);
const error = ref("");

const changed = computed(() => (loaded.value ? FIELDS.filter((f) => draft.value[f.key] !== loaded.value!.values[f.key]) : []));
const isCustom = (key: string): boolean => (loaded.value ? draft.value[key] !== loaded.value.defaults[key] : false);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    loaded.value = await agentsAdminClient.prompts();
    draft.value = { ...loaded.value.values };
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) void load();
    else confirming.value = discarding.value = false;
  },
  { immediate: true },
);

function reset(key: string): void {
  if (loaded.value) draft.value = { ...draft.value, [key]: loaded.value.defaults[key] ?? "" };
}

/** Unsaved text asks before the drawer closes. */
function requestClose(): void {
  if (changed.value.length) discarding.value = true;
  else emit("close");
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    // Only what changed; a text equal to its default is sent as-is and ai_agent drops the override.
    const changes = Object.fromEntries(changed.value.map((f) => [f.key, draft.value[f.key] ?? ""]));
    loaded.value = await agentsAdminClient.setPrompts(changes);
    draft.value = { ...loaded.value.values };
    confirming.value = false;
    emit("saved");
    emit("close");
  } catch (err) {
    confirming.value = false;
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <RecordDrawer :open="open" title="Shared prompts" :busy="saving" @close="requestClose">
    <div class="shared">
      <p class="intro">Text every agent's system prompt is built from. Saving restarts every agent.</p>
      <p v-if="loading" class="muted">Loading…</p>
      <template v-else-if="loaded">
        <label v-for="f in FIELDS" :key="f.key" class="field" :data-key="f.key">
          <span class="label">
            {{ f.label }}
            <span v-if="isCustom(f.key)" class="dot" title="Differs from the default" aria-label="Differs from the default">●</span>
            <button v-if="isCustom(f.key)" type="button" class="reset" :data-test="`reset-${f.key}`" @click.prevent="reset(f.key)">Reset to default</button>
          </span>
          <textarea v-model="draft[f.key]" :data-test="f.key" :rows="f.rows" />
          <small>{{ f.help }}</small>
        </label>
      </template>
      <ActionMessage v-if="error" kind="error" :text="error" data-test="prompts-error" />
    </div>
    <template #footer>
      <button type="button" class="chip" :disabled="saving" @click="requestClose">Close</button>
      <button type="button" class="primary" data-test="save-prompts" :disabled="saving || changed.length === 0" @click="confirming = true">Save</button>
    </template>
  </RecordDrawer>
  <ConfirmModal
    :open="confirming"
    title="Restart every agent?"
    :message="`Saving changes ${changed.map((f) => f.label).join(', ')}. Every agent restarts to apply it, and a chat being answered right now is cut off.`"
    confirm-label="Save and restart"
    :busy="saving"
    @confirm="save"
    @close="confirming = false"
  />
  <ConfirmModal
    :open="discarding"
    title="Discard changes?"
    message="Your changes will be lost."
    confirm-label="Discard changes"
    @confirm="discarding = false; emit('close')"
    @close="discarding = false"
  />
</template>

<style scoped>
.shared { display: grid; gap: 12px; padding-block-start: 4px; }
.intro, .muted { margin: 0; color: var(--muted); font-size: 0.9em; }
.field { display: grid; gap: 4px; font-size: 0.9em; }
.label { display: flex; align-items: center; gap: 8px; color: var(--muted); }
.dot { color: var(--accent); font-size: 0.7em; }
.reset { margin-left: auto; padding: 0; border: none; background: none; color: var(--accent); font: inherit; font-size: 0.85em; cursor: pointer; }
small { color: var(--muted); font-size: 0.8em; }
textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
  font: inherit;
  resize: vertical;
}
.error { margin: 0; color: var(--danger); }
:is(button, textarea):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
