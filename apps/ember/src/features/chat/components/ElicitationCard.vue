<script setup lang="ts">
import { computed, nextTick, reactive, ref, useId } from "vue";
import { ToggleSwitch, copyText } from "@citadel/ui";
import type { ElicitationAction, ElicitationField, ElicitationValue, PendingElicitation } from "../../../api/types";

/** A question an outside server asks mid-answer: a short form, or a link to
 * open. The server's text is shown as plain text. The agent confirms with an
 * elicitation_resolved event, which removes the card. */

const props = defineProps<{ pending: PendingElicitation; answering: boolean; problem?: string }>();
const emit = defineEmits<{
  answer: [id: string, action: ElicitationAction, content?: Record<string, ElicitationValue>];
}>();

const uid = useId();
const form = ref<HTMLFormElement | null>(null);
const fields = computed(() => props.pending.fields ?? []);
// Typed text stays text until Send; switches and ticks keep their own type.
const values = reactive<Record<string, string | boolean | string[]>>(
  Object.fromEntries(
    (props.pending.fields ?? []).map((f) => [f.name, f.kind === "boolean" ? false : f.kind === "multi_choice" ? [] : ""]),
  ),
);
const errors = reactive<Record<string, string>>({});
const sent = ref<ElicitationAction | "">("");

// Legion names the field first ("Name: this field is required."), so it is shown there.
const problemField = computed(() => fields.value.find((f) => props.problem?.startsWith(`${f.label}: `)));
const formProblem = computed(() => (problemField.value ? "" : (props.problem ?? "")));
function errorFor(field: ElicitationField): string {
  if (errors[field.name]) return errors[field.name]!;
  return problemField.value === field ? props.problem!.slice(field.label.length + 2) : "";
}
function describedBy(field: ElicitationField, index: number): string | undefined {
  const ids = [field.description ? `${uid}-${index}-help` : "", errorFor(field) ? `${uid}-${index}-error` : ""];
  return ids.filter(Boolean).join(" ") || undefined;
}

function choose(name: string, value: string, on: boolean): void {
  const chosen = (values[name] as string[]).filter((item) => item !== value);
  values[name] = on ? [...chosen, value] : chosen;
}

function read(field: ElicitationField): { value?: ElicitationValue; error?: string } {
  const raw = values[field.name]!;
  if (typeof raw === "boolean") return { value: raw };
  if (Array.isArray(raw)) {
    if (!raw.length) return field.required ? { error: "Choose at least one." } : {};
    if (field.min !== undefined && raw.length < field.min) return { error: `Choose at least ${field.min}.` };
    if (field.max !== undefined && raw.length > field.max) return { error: `Choose at most ${field.max}.` };
    return { value: [...raw] };
  }
  if (raw === "") return field.required ? { error: "This field is required." } : {};
  if (field.kind !== "number" && field.kind !== "integer") return { value: raw };
  const number = Number(raw);
  if (!raw.trim() || !Number.isFinite(number) || (field.kind === "integer" && !Number.isInteger(number))) {
    return { error: field.kind === "integer" ? "Enter a whole number." : "Enter a number." };
  }
  if (field.min !== undefined && number < field.min) return { error: `Enter at least ${field.min}.` };
  if (field.max !== undefined && number > field.max) return { error: `Enter at most ${field.max}.` };
  return { value: number };
}

function answer(action: ElicitationAction, content?: Record<string, ElicitationValue>): void {
  if (props.answering) return;
  sent.value = action;
  emit("answer", props.pending.id, action, content);
}

async function submit(): Promise<void> {
  if (props.pending.mode !== "form") return;
  const content: Record<string, ElicitationValue> = {};
  let invalid = false;
  for (const field of fields.value) {
    const { value, error } = read(field);
    errors[field.name] = error ?? "";
    if (error) invalid = true;
    else if (value !== undefined) content[field.name] = value;
  }
  if (invalid) {
    await nextTick();
    form.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    return;
  }
  answer("accept", content);
}

// URL mode: only an https link is offered, with its site in punycode so a look-alike name shows.
const link = computed(() => {
  try {
    const parsed = new URL(props.pending.url ?? "");
    return parsed.protocol === "https:" ? { href: props.pending.url!, site: parsed.hostname } : null;
  } catch {
    return null;
  }
});
const followed = ref(false);
const copyLabel = ref("Copy link");
async function copy(): Promise<void> {
  const copied = await copyText(link.value!.href);
  copyLabel.value = copied ? "Copied" : "Copy failed";
  if (copied) followed.value = true;
}
</script>

<template>
  <form ref="form" class="elicitation-card" :aria-label="`${pending.server} has a question`" novalidate @submit.prevent="submit">
    <header>
      <strong>{{ pending.server }} asks</strong>
      <span class="note">{{ [pending.agent_label, pending.tool].filter(Boolean).join(" · ") }}</span>
    </header>
    <p class="message">{{ pending.message }}</p>

    <template v-if="pending.mode === 'url'">
      <template v-if="link">
        <p class="site">Site: <strong>{{ link.site }}</strong></p>
        <p class="url" @copy="followed = true">{{ link.href }}</p>
        <div class="buttons">
          <a class="open" :href="link.href" target="_blank" rel="noopener noreferrer" @click="followed = true" @auxclick="followed = true">Open link</a>
          <button type="button" class="copy-link" @click="copy">{{ copyLabel }}</button>
        </div>
        <p class="note">Open the link, finish there, then press Continue.</p>
      </template>
      <p v-else class="error" role="alert">This link cannot be opened safely.</p>
    </template>

    <template v-else>
      <div v-for="(field, i) in fields" :key="field.name" class="field">
        <ToggleSwitch
          v-if="field.kind === 'boolean'"
          small
          :checked="values[field.name] === true"
          :disabled="answering"
          :aria-describedby="describedBy(field, i)"
          :aria-invalid="!!errorFor(field)"
          @change="values[field.name] = ($event.target as HTMLInputElement).checked"
        >{{ field.label }}</ToggleSwitch>
        <fieldset v-else-if="field.kind === 'multi_choice'" :aria-describedby="describedBy(field, i)">
          <legend>{{ field.label }}<span v-if="field.required"><span aria-hidden="true"> *</span><span class="sr-only"> required</span></span></legend>
          <div v-for="o in field.options" :key="o.value" class="tick">
            <ToggleSwitch
              small
              :checked="(values[field.name] as string[]).includes(o.value)"
              :disabled="answering"
              :aria-invalid="!!errorFor(field)"
              @change="choose(field.name, o.value, ($event.target as HTMLInputElement).checked)"
            >{{ o.label }}</ToggleSwitch>
          </div>
        </fieldset>
        <template v-else>
          <label :for="`${uid}-${i}`">{{ field.label }}<span v-if="field.required" aria-hidden="true"> *</span></label>
          <select v-if="field.kind === 'choice'" :id="`${uid}-${i}`" v-model="values[field.name]" :disabled="answering" :aria-required="field.required" :aria-invalid="!!errorFor(field)" :aria-describedby="describedBy(field, i)">
            <option value="">Choose…</option>
            <option v-for="o in field.options" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <textarea v-else-if="field.kind === 'text' && (field.max_length ?? 0) > 200" :id="`${uid}-${i}`" :value="String(values[field.name])" @input="values[field.name] = ($event.target as HTMLTextAreaElement).value" rows="3" :maxlength="field.max_length" :disabled="answering" :aria-required="field.required" :aria-invalid="!!errorFor(field)" :aria-describedby="describedBy(field, i)" />
          <input v-else :id="`${uid}-${i}`" v-model="values[field.name]" type="text" :inputmode="field.kind === 'integer' ? 'numeric' : field.kind === 'number' ? 'decimal' : 'text'" :maxlength="field.max_length" autocomplete="off" :disabled="answering" :aria-required="field.required" :aria-invalid="!!errorFor(field)" :aria-describedby="describedBy(field, i)" />
        </template>
        <p v-if="field.description" :id="`${uid}-${i}-help`" class="note">{{ field.description }}</p>
        <p v-if="errorFor(field)" :id="`${uid}-${i}-error`" class="error" role="alert">{{ errorFor(field) }}</p>
      </div>
      <p class="warning">Do not enter passwords or keys here.</p>
    </template>

    <p v-if="formProblem" class="error" role="alert">{{ formProblem }}</p>
    <div class="buttons">
      <button v-if="pending.mode === 'url'" type="button" class="submit" :aria-busy="answering && sent === 'accept'" :disabled="!followed || answering" @click="answer('accept')">Continue</button>
      <button v-else type="submit" class="submit" :aria-busy="answering && sent === 'accept'" :disabled="answering">Send</button>
      <button type="button" class="decline" :aria-busy="answering && sent === 'decline'" :disabled="answering" @click="answer('decline')">Decline</button>
      <button type="button" class="cancel" :aria-busy="answering && sent === 'cancel'" :disabled="answering" @click="answer('cancel')">Cancel</button>
    </div>
  </form>
</template>

<style scoped src="./chatShared.css"></style>
<style scoped>
.elicitation-card {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--accent) 6%, var(--surface));
}
header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
}
p {
  margin: 0;
  overflow-wrap: anywhere;
}
.message {
  white-space: pre-wrap;
}
.url {
  user-select: all;
  font-family: var(--mono);
  font-size: 0.8em;
}
.field {
  display: grid;
  gap: 4px;
  min-width: 0;
}
fieldset {
  display: grid;
  gap: 4px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
legend {
  padding: 0;
}
.tick {
  display: flex;
  align-items: center;
  gap: 8px;
}
input[type="text"],
textarea,
select {
  min-width: 0;
  max-width: 100%;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font: inherit;
  font-size: 0.9em;
  color: var(--text);
  background: var(--bg);
}
.field [aria-invalid="true"] {
  border-color: var(--danger);
}
input:focus-visible,
textarea:focus-visible,
select:focus-visible,
.open:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.note {
  font-size: 0.75em;
  color: var(--muted);
}
.warning {
  font-size: 0.8em;
}
.error {
  font-size: 0.8em;
  color: var(--danger);
}
.open {
  display: inline-flex;
  align-items: center;
  padding: 5px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  font-size: 0.85em;
  color: var(--text);
  text-decoration: none;
}
.buttons .submit {
  border-color: var(--accent);
  color: var(--accent-contrast);
  background: var(--accent);
}
.buttons button:disabled {
  cursor: default;
  opacity: 0.45;
}
@media (pointer: coarse), (max-width: 767px) {
  .open,
  .buttons button,
  .tick,
  select,
  input[type="text"] {
    min-height: 44px;
  }
  select,
  textarea,
  input[type="text"] {
    font-size: 16px;
  }
}
</style>
