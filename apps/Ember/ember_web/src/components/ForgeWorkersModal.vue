<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  FORGE_LABEL_MAX,
  type ForgeCreatedWorker,
  type ForgePlans,
  type ForgeProvider,
  type ForgeWorker,
} from "../api/ForgeClient";
import BaseModal from "./BaseModal.vue";
import CopyButton from "./CopyButton.vue";
import SegmentedControl from "./SegmentedControl.vue";

const props = defineProps<{
  open: boolean;
  workers: ForgeWorker[];
  plans: ForgePlans;
  canEditPlans: boolean;
  busy: boolean;
  error: string;
  /** Set right after a worker was made: shows its one-time token. */
  created: ForgeCreatedWorker | null;
}>();
const emit = defineEmits<{
  close: [];
  create: [provider: ForgeProvider, label: string];
  remove: [worker: ForgeWorker];
  savePlans: [provider: ForgeProvider, plans: string[]];
  dismissToken: [];
}>();

const PROVIDERS = [
  { value: "claude", label: "Claude" },
  { value: "codex", label: "Codex" },
] as const;
const LABEL = /^[A-Za-z0-9_-]{1,24}$/;

const provider = ref<ForgeProvider>("claude");
const label = ref("claude");
let labelEdited = false;
const planText = ref<Record<ForgeProvider, string>>({ claude: "", codex: "" });

const labelOk = computed(() => LABEL.test(label.value.trim()));
const command = computed(() =>
  props.created ? `run.bat pair ${window.location.origin} ${props.created.token} --provider ${props.created.provider}` : "",
);
const reported = computed(() => {
  const found: Record<ForgeProvider, string[]> = { claude: [], codex: [] };
  for (const w of props.workers) if (w.reported_plan && !found[w.provider].includes(w.reported_plan)) found[w.provider].push(w.reported_plan);
  return found;
});

watch(provider, (next) => {
  if (!labelEdited) label.value = next;
});

watch(
  () => [props.open, props.plans] as const,
  ([open]) => {
    if (!open) return;
    planText.value = { claude: props.plans.claude.join(", "), codex: props.plans.codex.join(", ") };
  },
  { immediate: true, deep: true },
);

function onLabelInput(): void {
  labelEdited = true;
}

function create(): void {
  if (labelOk.value && !props.busy) emit("create", provider.value, label.value.trim());
}

function savePlans(which: ForgeProvider): void {
  const list = planText.value[which].split(",").map((p) => p.trim()).filter(Boolean);
  emit("savePlans", which, list);
}
</script>

<template>
  <BaseModal :open="open" title="Workers" wide @close="emit('close')">
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <section v-if="created" class="token" aria-live="polite">
      <h4>Pair @{{ created.label }}</h4>
      <p>
        Run this on the computer where {{ created.provider === "claude" ? "Claude Code" : "Codex" }} is logged in, from the
        <code>ember_worker</code> folder. The token is shown once; make a new worker if you lose it.
      </p>
      <div class="command-row">
        <code class="command">{{ command }}</code>
        <CopyButton :text="command" label="Copy the command" />
      </div>
      <button type="button" class="done" @click="emit('dismissToken')">Done</button>
    </section>

    <section>
      <h4>Your workers</h4>
      <ul v-if="workers.length" class="workers">
        <li v-for="w in workers" :key="w.id">
          <div class="line">
            <strong class="who">@{{ w.label }}</strong>
            <span class="muted">{{ w.provider }} · {{ w.reported_plan ?? "plan not reported yet" }}</span>
            <button type="button" class="remove" :aria-label="`Remove @${w.label}`" :disabled="busy" @click="emit('remove', w)">Remove</button>
          </div>
          <div class="states">
            <span class="state" :class="{ ok: w.online }">
              <svg v-if="w.online" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5" /></svg>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><circle cx="12" cy="12" r="8" /></svg>
              {{ w.online ? "Online" : "Offline" }}
            </span>
            <span class="state" :class="{ ok: w.eligible }">
              <svg v-if="w.eligible" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5" /></svg>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              {{ w.eligible ? "Eligible" : (w.problem ?? "Not eligible") }}
            </span>
          </div>
        </li>
      </ul>
      <p v-else class="muted">No workers yet. A worker is your own Claude Code or Codex, running on your computer.</p>
    </section>

    <section>
      <h4>Add a worker</h4>
      <form class="add" @submit.prevent="create">
        <SegmentedControl v-model="provider" :options="PROVIDERS" aria-label="Provider" />
        <label class="field">
          <span>Name to @mention</span>
          <input v-model="label" type="text" :maxlength="FORGE_LABEL_MAX" autocomplete="off" spellcheck="false" @input="onLabelInput" />
        </label>
        <p v-if="!labelOk" class="hint">Use 1 to 24 letters, digits, - or _.</p>
        <button type="submit" class="primary" :disabled="!labelOk || busy" :aria-busy="busy">Create worker</button>
      </form>
    </section>

    <section v-if="canEditPlans">
      <h4>Eligible plans</h4>
      <p class="muted">Only workers whose CLI reports one of these plans can join a group. Separate plans with commas.</p>
      <form v-for="p in PROVIDERS" :key="p.value" class="plans" :data-provider="p.value" @submit.prevent="savePlans(p.value)">
        <label class="field">
          <span>{{ p.label }}</span>
          <input v-model="planText[p.value]" type="text" :data-provider="p.value" autocomplete="off" spellcheck="false" placeholder="for example: max, pro" />
        </label>
        <button type="submit" class="secondary" :disabled="busy">Save</button>
        <p v-if="reported[p.value].length" class="hint">Reported by your workers: {{ reported[p.value].join(", ") }}</p>
      </form>
    </section>
  </BaseModal>
</template>

<style scoped>
section {
  margin-bottom: 18px;
}
h4 {
  margin: 0 0 8px;
  font-size: 1em;
}
.error {
  margin: 0 0 12px;
  color: var(--danger);
}
.muted,
.hint {
  color: var(--muted);
  font-size: 0.85em;
  margin: 0;
}
.workers {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.workers li {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  padding: 8px 10px;
}
.line,
.states {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
}
.states {
  margin-top: 4px;
}
.who {
  color: var(--accent);
}
.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 0.85em;
}
.state.ok {
  color: var(--success);
}
.state svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
button.remove {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: var(--danger);
  font: inherit;
  font-size: 0.85em;
  text-decoration: underline;
  cursor: pointer;
}
.add,
.plans {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 180px;
}
.field input {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
}
.field input:focus {
  border-color: var(--accent);
}
button.primary,
button.secondary,
button.done {
  border-radius: var(--radius-full);
  padding: 8px 18px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button.primary,
button.done {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-contrast);
}
button.secondary {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.token {
  border: 1px solid var(--accent);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--accent) 8%, var(--bg));
  padding: 12px 14px;
}
.token h4 {
  margin-top: 0;
}
.command-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 12px;
}
code.command {
  flex: 1;
  background: var(--code-bg);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  font-family: var(--mono);
  font-size: 0.85em;
  overflow-wrap: anywhere;
}
</style>
