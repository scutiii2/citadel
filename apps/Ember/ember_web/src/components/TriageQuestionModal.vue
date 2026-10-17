<script setup lang="ts">
import { computed, ref } from "vue";
import {
  TRIAGE_DESCRIPTION_MAX,
  TRIAGE_MAX_OPTIONS,
  TRIAGE_MIN_OPTIONS,
  TRIAGE_QUESTION_MAX,
  TRIAGE_TEXT_MAX,
  TRIAGE_TITLE_MAX,
  triageClient,
  type TriageForm,
  type TriageKind,
} from "../api/TriageClient";
import { errorMessage } from "../utils/errors";
import BaseModal from "./BaseModal.vue";
import SegmentedControl from "./SegmentedControl.vue";

/** A form for a typed question to the Triage Assistant (Laya), asked directly and not through the
 * orchestrator. A multiple choice option is a description plus a one-word title; a small model
 * writes the titles from the descriptions on request. `submit` asks and saves the exchange in the
 * chat; the dialog closes when it resolves and shows what it throws. */
const props = defineProps<{ open: boolean; submit: (form: TriageForm) => Promise<void> }>();
const emit = defineEmits<{ close: [] }>();

interface OptionRow {
  key: number;
  description: string;
  title: string;
}

const TITLE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
const KINDS: readonly { value: TriageKind; label: string }[] = [
  { value: "choice", label: "Multiple choice" },
  { value: "yes_no", label: "Yes or no" },
];

let nextKey = 1;
const blankRow = (): OptionRow => ({ key: nextKey++, description: "", title: "" });

const kind = ref<TriageKind>("choice");
const text = ref("");
const question = ref("");
const rows = ref<OptionRow[]>([blankRow(), blankRow()]);
const titling = ref(false);
const asking = ref(false);
const error = ref("");

const isChoice = computed(() => kind.value === "choice");
const busy = computed(() => titling.value || asking.value);
const descriptionsFilled = computed(() => rows.value.every((r) => r.description.trim() !== ""));
const titles = computed(() => rows.value.map((r) => r.title.trim()));
const titlesValid = computed(
  () =>
    titles.value.every((t) => TITLE_PATTERN.test(t) && t.length <= TRIAGE_TITLE_MAX) &&
    new Set(titles.value.map((t) => t.toLowerCase())).size === titles.value.length,
);
const canAsk = computed(
  () =>
    !busy.value &&
    text.value.trim() !== "" &&
    question.value.trim() !== "" &&
    (!isChoice.value || (descriptionsFilled.value && titlesValid.value)),
);
const titleHint = computed(() => {
  if (!isChoice.value || !descriptionsFilled.value || titlesValid.value) return "";
  return titles.value.some((t) => t === "") ? "Generate titles, or type one word for each option." : "Each option needs its own one-word title.";
});

function addRow(): void {
  if (rows.value.length < TRIAGE_MAX_OPTIONS) rows.value.push(blankRow());
}

function removeRow(key: number): void {
  if (rows.value.length > TRIAGE_MIN_OPTIONS) rows.value = rows.value.filter((r) => r.key !== key);
}

async function generateTitles(): Promise<void> {
  if (busy.value || !descriptionsFilled.value) return;
  titling.value = true;
  error.value = "";
  try {
    const written = await triageClient.titles(rows.value.map((r) => r.description.trim()));
    rows.value.forEach((row, i) => (row.title = written[i] ?? row.title));
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    titling.value = false;
  }
}

function reset(): void {
  text.value = "";
  question.value = "";
  rows.value = [blankRow(), blankRow()];
  error.value = "";
}

async function ask(): Promise<void> {
  if (!canAsk.value) return;
  asking.value = true;
  error.value = "";
  try {
    await props.submit({
      kind: kind.value,
      text: text.value.trim(),
      question: question.value.trim(),
      options: isChoice.value ? rows.value.map((r) => ({ title: r.title.trim().toLowerCase(), description: r.description.trim() })) : [],
    });
    reset();
    emit("close");
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    asking.value = false;
  }
}

function close(): void {
  if (!asking.value) emit("close");
}
</script>

<template>
  <BaseModal :open="open" title="Ask the Triage Assistant" @close="close">
    <form class="form" @submit.prevent="ask">
      <SegmentedControl v-model="kind" :options="KINDS" aria-label="Kind of question" />
      <label>
        Text to read
        <textarea v-model="text" rows="4" :maxlength="TRIAGE_TEXT_MAX" placeholder="The message, ticket or note the question is about" />
        <small class="count">{{ text.length.toLocaleString() }} / {{ TRIAGE_TEXT_MAX.toLocaleString() }}</small>
      </label>
      <label>
        Question
        <input
          v-model="question"
          type="text"
          :maxlength="TRIAGE_QUESTION_MAX"
          autocomplete="off"
          :placeholder="isChoice ? 'Which area does this belong to?' : 'Is this a problem?'"
        />
      </label>

      <fieldset v-if="isChoice" class="options">
        <legend>Options</legend>
        <div v-for="(row, i) in rows" :key="row.key" class="option">
          <input
            v-model="row.description"
            type="text"
            :maxlength="TRIAGE_DESCRIPTION_MAX"
            autocomplete="off"
            :aria-label="`Option ${i + 1} description`"
            placeholder="Describe this option"
          />
          <input
            v-model="row.title"
            class="title"
            type="text"
            :maxlength="TRIAGE_TITLE_MAX"
            autocomplete="off"
            :aria-label="`Option ${i + 1} title`"
            placeholder="title"
          />
          <button
            type="button"
            class="link"
            :disabled="rows.length <= TRIAGE_MIN_OPTIONS"
            :aria-label="`Remove option ${i + 1}`"
            @click="removeRow(row.key)"
          >
            ×
          </button>
        </div>
        <div class="option-actions">
          <button type="button" class="ghost" :disabled="rows.length >= TRIAGE_MAX_OPTIONS" @click="addRow">Add option</button>
          <button type="button" class="ghost" :disabled="busy || !descriptionsFilled" :aria-busy="titling" @click="generateTitles">
            {{ titling ? "Writing titles …" : "Generate titles" }}
          </button>
        </div>
        <small v-if="titleHint" class="hint">{{ titleHint }}</small>
      </fieldset>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="buttons">
        <button type="button" class="ghost" :disabled="asking" @click="close">Cancel</button>
        <button type="submit" class="primary" :disabled="!canAsk" :aria-busy="asking">{{ asking ? "Asking …" : "Ask" }}</button>
      </div>
    </form>
  </BaseModal>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85em;
  color: var(--muted);
}
.form input,
.form textarea {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  outline: none;
  resize: vertical;
  color: var(--text);
  background: var(--bg);
  font: inherit;
}
.form input:focus,
.form textarea:focus {
  border-color: var(--accent);
}
.count {
  align-self: flex-end;
}
.options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  border: none;
}
.options legend {
  padding: 0;
  margin-bottom: 6px;
  font-size: 0.85em;
  color: var(--muted);
}
.option {
  display: flex;
  align-items: center;
  gap: 6px;
}
.option input {
  flex: 1;
  min-width: 0;
}
.option input.title {
  flex: 0 0 8.5em;
  font-family: var(--mono);
}
.option-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.hint {
  color: var(--muted);
}
.error {
  margin: 0;
  font-size: 0.9em;
  color: var(--danger);
}
.buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.ghost,
.primary {
  padding: 5px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  cursor: pointer;
}
.ghost {
  color: var(--muted);
  background: transparent;
}
.ghost:hover:not(:disabled) {
  color: var(--text);
}
.primary {
  border-color: var(--accent);
  color: var(--accent-contrast);
  background: var(--accent);
}
.ghost:disabled,
.primary:disabled {
  cursor: default;
  opacity: 0.4;
}
.link {
  padding: 2px 8px;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 1.2em;
  line-height: 1;
  color: var(--muted);
  background: transparent;
}
.link:hover:not(:disabled) {
  color: var(--danger);
}
.link:disabled {
  cursor: default;
  opacity: 0.3;
}
</style>
