<script setup lang="ts">
import PageLayout from "../../components/layout/PageLayout.vue";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { McpServerClient } from "../../api/tools/McpServerClient";
import { onBeforeRouteLeave } from "vue-router";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import CopyButton from "../../components/ui/buttons/CopyButton.vue";
import SegmentedControl from "../../components/ui/forms/SegmentedControl.vue";
import ToggleSwitch from "../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage } from "../../utils/errors";

/** Random passwords, passphrases, PINs and TOTP secrets and codes, made by
 * mcp_server's generator tools. Nothing is stored; a value is shown once. */

type Tab = "password" | "passphrase" | "pin" | "totp-secret" | "totp";
interface Result {
  value: string;
  detail: string;
  bits: number | null;
  /** Seconds until a TOTP code changes. */
  remaining: number | null;
}

const TABS = [
  { value: "password", label: "Password" },
  { value: "passphrase", label: "Passphrase" },
  { value: "pin", label: "PIN" },
  { value: "totp-secret", label: "TOTP secret" },
  { value: "totp", label: "TOTP code" },
] as const;
/** The tool behind each tab and the field of its result that holds the value. */
const TOOLS: Record<Tab, { tool: string; field: string }> = {
  password: { tool: "tool_gen_generatePassword", field: "password" },
  passphrase: { tool: "tool_gen_generatePassphrase", field: "passphrase" },
  pin: { tool: "tool_gen_generatePin", field: "pin" },
  "totp-secret": { tool: "tool_gen_generateTotpSecret", field: "secret" },
  totp: { tool: "tool_gen_getTotpCode", field: "code" },
};
/** Strength bar scale: 128 bits and above counts as full. */
const FULL_BITS = 128;

const checked = (event: Event): boolean => (event.target as HTMLInputElement).checked;

const server = new McpServerClient();
const tab = ref<Tab>("password");

const options = reactive({
  password: { length: 20, use_upper: true, use_lower: true, use_digits: true, use_symbols: true, exclude_ambiguous: false },
  passphrase: { words: 6, separator: "-", capitalize: false, add_number: false },
  pin: { length: 6 },
  totpSecret: { issuer: "", account: "" },
  totp: { secret: "", digits: 6, period: 30 },
});
const results = reactive<Partial<Record<Tab, Result>>>({});
const busy = ref(false);
const error = ref("");
const revealed = ref(false);
const optionsOpen = ref(false);
let sequence = 0;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

const result = computed(() => results[tab.value]);
const typeLabel = computed(() => TABS.find(item => item.value === tab.value)!.label);
const generateLabel = computed(() => busy.value ? "Generating…" : tab.value === "totp" ? "Generate code" : `${result.value ? "Regenerate" : "Generate"} ${typeLabel.value.toLowerCase()}`);
const optionSummary = computed(() => {
  switch (tab.value) {
    case "password": return `${options.password.length} characters · ${[options.password.use_upper, options.password.use_lower, options.password.use_digits, options.password.use_symbols].filter(Boolean).length} character types`;
    case "passphrase": return `${options.passphrase.words} words`;
    case "pin": return `${options.pin.length} digits`;
    case "totp-secret": return "Issuer and account optional";
    case "totp": return `${options.totp.digits} digits · ${options.totp.period}-second period`;
  }
});
const resultMeta = computed(() => {
  if (!result.value) return "";
  if (tab.value === "password") return `${result.value.value.length} characters`;
  if (tab.value === "pin" || tab.value === "totp") return `${result.value.value.length} digits`;
  return tab.value === "totp-secret" ? "Base32 secret" : "Passphrase";
});
const strength = computed(() => Math.min(100, Math.round(((result.value?.bits ?? 0) / FULL_BITS) * 100)));
const characterTypes = computed(() => {
  const o = options.password;
  return o.use_upper || o.use_lower || o.use_digits || o.use_symbols;
});
const canRun = computed(() => {
  if (busy.value) return false;
  if (tab.value === "password") return characterTypes.value;
  if (tab.value === "totp") return options.totp.secret.trim() !== "";
  return true;
});
/** Every generated value stays masked until Reveal is pressed. A revealed TOTP code is
 * shown in groups of three, like an authenticator app. */
const shown = computed(() => {
  const r = result.value;
  if (!r) return "";
  if (!revealed.value) return "•".repeat(Math.min(r.value.length, 32));
  return tab.value === "totp" ? r.value.replace(/(\d{3})(?=\d)/g, "$1 ") : r.value;
});

/** Filled-track percentage for a range input, set as the `--fill` custom property. */
function fill(value: number, min: number, max: number): Record<string, string> {
  return { "--fill": `${((value - min) / (max - min)) * 100}%` };
}

/** The form button: a fresh value starts hidden again. */
function generate(): void {
  revealed.value = false;
  void run();
}

function argsFor(which: Tab): Record<string, unknown> {
  switch (which) {
    case "password": return { ...options.password };
    case "passphrase": return { ...options.passphrase };
    case "pin": return { ...options.pin };
    case "totp-secret": return { ...options.totpSecret };
    case "totp": return { ...options.totp };
  }
}

function clearTimer(): void {
  if (refreshTimer !== null) clearTimeout(refreshTimer);
  refreshTimer = null;
}

async function run(which: Tab = tab.value): Promise<void> {
  const mine = ++sequence;
  clearTimer();
  busy.value = true;
  error.value = "";
  try {
    const outcome = await server.runTool(TOOLS[which].tool, argsFor(which));
    if (mine !== sequence) return; // a newer request replaced this one
    const data = outcome.structured;
    if (outcome.isError || !data || typeof data[TOOLS[which].field] !== "string") {
      error.value = outcome.text || "The generator returned no value.";
      return;
    }
    const bits = typeof data.entropy_bits === "number" ? data.entropy_bits : null;
    const remaining = typeof data.seconds_remaining === "number" ? data.seconds_remaining : null;
    results[which] = {
      value: data[TOOLS[which].field] as string,
      detail: typeof data.message === "string" ? data.message : "",
      bits,
      remaining,
    };
    if (which === "totp" && remaining !== null) {
      // Ask for the next code the moment this one stops being valid.
      refreshTimer = setTimeout(() => void run("totp"), remaining * 1000 + 250);
    }
  } catch (err) {
    if (mine === sequence) error.value = errorMessage(err);
  } finally {
    if (mine === sequence) busy.value = false;
  }
}

/** Throws away every generated value (and stops a TOTP refresh and a request in flight). */
function discard(): void {
  sequence++;
  clearTimer();
  busy.value = false;
  for (const key of Object.keys(results) as Tab[]) delete results[key];
}

// Nothing is generated on its own: only the Generate button makes a value, and
// a value does not outlive its tab or the page.
watch(tab, () => {
  revealed.value = false;
  optionsOpen.value = tab.value === "totp";
  error.value = "";
  discard();
});

/** The leave warning: asked before a tab change or a page change drops a generated value. */
const leaving = ref<{ page: boolean; resolve: (leave: boolean) => void } | null>(null);

function confirmLeave(page: boolean): Promise<boolean> {
  return new Promise((resolve) => {
    leaving.value = { page, resolve };
  });
}

function answerLeave(leave: boolean): void {
  leaving.value?.resolve(leave);
  leaving.value = null;
}

async function requestTab(next: Tab): Promise<void> {
  if (next === tab.value) return;
  if (!result.value || (await confirmLeave(false))) tab.value = next;
}

function selectType(event: Event): void {
  const select = event.target as HTMLSelectElement;
  const next = select.value as Tab;
  select.value = tab.value; // Keep the current selection until discard is confirmed.
  void requestTab(next);
}

onBeforeRouteLeave(() => (result.value ? confirmLeave(true) : true));

onBeforeUnmount(() => {
  sequence++;
  clearTimer();
});
</script>


<template>
  <PageLayout title="Generator" description="Passwords, passphrases, PINs and one-time codes." class="generator" wide fill>
    <form class="generator-workspace" @submit.prevent="canRun && generate()">
      <div class="type-picker">
        <div class="desktop-types"><SegmentedControl :model-value="tab" aria-label="Generator type" :options="TABS" @update:model-value="requestTab" /></div>
        <label class="mobile-type">Generator type
          <select :value="tab" aria-label="Generator type" @change="selectType"><option v-for="item in TABS" :key="item.value" :value="item.value">{{ item.label }}</option></select>
        </label>
      </div>
      <div class="work-scroll">
        <section class="result-panel" aria-label="Generated value">
          <h3>{{ typeLabel }}</h3>
          <p class="intro">{{ tab === 'totp' ? 'Get a one-time code from your secret.' : tab === 'totp-secret' ? 'Create a secret for setting up one-time codes.' : 'A random value, ready to copy.' }}</p>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <div v-if="result" class="result" aria-live="polite">
            <div class="value-panel">
              <p class="value-label">Generated {{ typeLabel.toLowerCase() }}</p>
              <code class="value" :class="{ code: tab === 'totp' }" data-testid="generated-value">{{ shown }}</code>
              <div class="result-actions">
                <span class="result-meta">{{ resultMeta }}<template v-if="result.bits !== null"> · {{ Math.round(result.bits) }} bits</template></span>
                <div class="result-buttons">
                  <button type="button" class="reveal" :aria-pressed="revealed" @click="revealed = !revealed"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>{{ revealed ? "Hide" : "Reveal" }}</button>
                  <CopyButton :key="result.value" :text="result.value" label="Copy value" />
                </div>
              </div>
            </div>
            <div v-if="result.bits !== null" class="strength" role="meter" aria-label="Strength" :aria-valuenow="Math.min(FULL_BITS, Math.max(0, Math.round(result.bits)))" aria-valuemin="0" :aria-valuemax="FULL_BITS" :aria-valuetext="Math.round(result.bits) + ' bits'">
              <span class="bar"><span class="fill" :style="{ width: strength + '%' }" /></span><span class="muted">{{ Math.round(result.bits) }} bits</span>
            </div>
            <p v-if="result.remaining !== null" class="result-detail">Changes in about {{ result.remaining }} s.</p>
            <p v-if="result.detail" class="result-detail">{{ result.detail }}</p>
            <p class="result-note">Copy your value before switching types or leaving this page.</p>
          </div>
          <p v-else-if="busy" class="muted" role="status">Generating…</p>
          <div v-else class="empty-result"><p class="hint">Nothing generated yet. Press {{ tab === 'totp' ? 'Generate code' : 'Generate' }}.</p><p v-if="tab === 'totp'" class="muted">Enter your secret in Options to generate a code.</p></div>
        </section>
        <section :class="['options-panel', { expanded: optionsOpen }]" aria-label="Generator options">
          <div class="desktop-options-heading"><h3>{{ typeLabel }} options</h3><p class="options-description">Adjust your next generated value.</p></div>
          <button type="button" class="options-disclosure" :aria-expanded="optionsOpen" aria-controls="generator-options" @click="optionsOpen = !optionsOpen"><span>Options</span><span class="options-summary">{{ optionSummary }}<svg viewBox="0 0 24 24" aria-hidden="true"><path :d="optionsOpen ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'" /></svg></span></button>
          <div id="generator-options" class="options-body">
            <template v-if="tab === 'password'">
            <label class="field">Length: {{ options.password.length }}
              <input v-model.number="options.password.length" type="range" min="8" max="128" :style="fill(options.password.length, 8, 128)" />
            </label>
            <ToggleSwitch small :checked="options.password.use_upper" @change="options.password.use_upper = checked($event)">Uppercase A-Z</ToggleSwitch>
            <ToggleSwitch small :checked="options.password.use_lower" @change="options.password.use_lower = checked($event)">Lowercase a-z</ToggleSwitch>
            <ToggleSwitch small :checked="options.password.use_digits" @change="options.password.use_digits = checked($event)">Digits 0-9</ToggleSwitch>
            <ToggleSwitch small :checked="options.password.use_symbols" @change="options.password.use_symbols = checked($event)">Symbols</ToggleSwitch>
            <ToggleSwitch small :checked="options.password.exclude_ambiguous" @change="options.password.exclude_ambiguous = checked($event)">Leave out look-alikes (I l 1 O 0 o)</ToggleSwitch>
            <p v-if="!characterTypes" class="error">Choose at least one kind of character.</p>
          </template>
          <template v-else-if="tab === 'passphrase'">
            <label class="field">Words: {{ options.passphrase.words }}
              <input v-model.number="options.passphrase.words" type="range" min="3" max="12" :style="fill(options.passphrase.words, 3, 12)" />
            </label>
            <label class="field">Separator
              <input v-model="options.passphrase.separator" type="text" maxlength="3" aria-label="Separator" />
            </label>
            <ToggleSwitch small :checked="options.passphrase.capitalize" @change="options.passphrase.capitalize = checked($event)">Capitalise each word</ToggleSwitch>
            <ToggleSwitch small :checked="options.passphrase.add_number" @change="options.passphrase.add_number = checked($event)">Add a digit</ToggleSwitch>
          </template>
          <template v-else-if="tab === 'pin'">
            <label class="field">Digits: {{ options.pin.length }}
              <input v-model.number="options.pin.length" type="range" min="4" max="12" :style="fill(options.pin.length, 4, 12)" />
            </label>
          </template>
          <template v-else-if="tab === 'totp-secret'">
            <label class="field">Issuer (optional)
              <input v-model="options.totpSecret.issuer" type="text" placeholder="Ember" />
            </label>
            <label class="field">Account (optional)
              <input v-model="options.totpSecret.account" type="text" placeholder="you@example.com" />
            </label>
          </template>
          <template v-else>
            <label class="field">Secret
              <input v-model="options.totp.secret" type="password" autocomplete="off" placeholder="Base32 secret" />
            </label>
            <label class="field">Digits
              <select v-model.number="options.totp.digits">
                <option :value="6">6</option>
                <option :value="7">7</option>
                <option :value="8">8</option>
              </select>
            </label>
            <label class="field">Period (seconds)
              <input v-model.number="options.totp.period" type="number" min="15" max="120" />
            </label>
          </template>
            <p class="options-note">Changes apply when you generate again.</p>
          </div>
        </section>
      </div>
      <footer class="generate-footer"><p>Generated values aren't saved.</p><button type="submit" class="primary" :disabled="!canRun" :aria-busy="busy"><svg v-if="!busy" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 13-2l2 7M4 12l2 7a8 8 0 0 0 13-2" /></svg>{{ generateLabel }}</button></footer>
    </form>
    <ConfirmModal :open="leaving !== null" title="Discard the generated value?" :message="`Generated values are not stored. Leaving this ${leaving?.page ? 'page' : 'tab'} removes the one you made, so copy it first if you still need it.`" confirm-label="Discard and leave" @confirm="answerLeave(true)" @close="answerLeave(false)" />
  </PageLayout>
</template>

<style scoped>
.generator-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 300px; grid-template-rows: auto minmax(0, 1fr) auto; grid-template-areas: 'type options' 'result options' 'footer options'; flex: 1; min-width: 0; min-height: 0; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.type-picker { grid-area: type; padding: 22px 24px 0; min-width: 0; }
.work-scroll { display: contents; }
.mobile-type { display: none; }
.result-panel { grid-area: result; padding: 30px 24px 24px; min-width: 0; min-height: 0; overflow-y: auto; }
h3 { margin: 0; font-size: 1em; font-weight: 600; }
.intro { margin: 8px 0 24px; font-size: .85em; color: var(--muted); }
.value-panel { padding: 22px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.value-label { margin: 0 0 14px; color: var(--muted); font-size: .75em; }
.value { display: block; min-width: 0; min-height: 40px; font: 500 1.25em/1.7 var(--mono); letter-spacing: .025em; overflow-wrap: anywhere; white-space: pre-wrap; }
.value.code { font-size: 1.6em; letter-spacing: .08em; }
.result-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 18px; flex-wrap: wrap; }
.result-meta { font-size: .75em; color: var(--muted); }
.result-buttons { display: flex; gap: 8px; }
.reveal, .result-buttons :deep(button.copy) { display: inline-flex; align-items: center; justify-content: center; gap: 7px; font: inherit; font-size: .8em; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--bg); color: var(--text); cursor: pointer; }
.result-buttons :deep(button.copy.idle)::after { content: 'Copy'; }
svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.strength { display: flex; align-items: center; gap: 10px; margin-top: 18px; font-size: .75em; color: var(--muted); }
.bar { flex: 1; height: 4px; border-radius: var(--radius-full); background: var(--border); overflow: hidden; }
.fill { display: block; height: 100%; background: var(--accent); transition: width .2s ease; }
.result-note, .result-detail { color: var(--muted); font-size: .8em; margin: 16px 0 0; overflow-wrap: anywhere; }
.empty-result { padding: 24px 20px; border: 1px dashed var(--border); border-radius: var(--radius-lg); color: var(--muted); font-size: .85em; }
.empty-result p { margin: 0; }
.empty-result p + p { margin-top: 12px; }
.options-panel { grid-area: options; min-width: 0; min-height: 0; overflow-y: auto; border-left: 1px solid var(--border); padding: 22px 18px; background: color-mix(in srgb, var(--surface) 45%, var(--bg)); }
.options-description { color: var(--muted); font-size: .75em; margin: 8px 0 24px; }
.options-disclosure { display: none; }
.options-body { display: grid; gap: 16px; }
.field { display: grid; gap: 8px; font-size: .85em; }
.field input:not([type=range]), .field select, .mobile-type select { font: inherit; width: 100%; min-width: 0; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 9px 11px; }
.options-body :deep(.toggle) { min-height: 34px; flex-direction: row-reverse; justify-content: space-between; gap: 12px; }
.options-body :deep(.toggle .text) { font-size: .85em; }
.options-note { color: var(--muted); font-size: .75em; margin: 8px 0 0; }
.generate-footer { grid-area: footer; margin: 0 24px 20px; padding-top: 18px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.generate-footer p { color: var(--muted); font-size: .75em; margin: 0; }
.primary { display: inline-flex; align-items: center; justify-content: center; gap: 8px; font: inherit; font-size: .85em; font-weight: 600; padding: 10px 18px; min-height: 44px; border: 1px solid var(--accent); border-radius: var(--radius-full); background: var(--accent); color: var(--accent-contrast); cursor: pointer; }
.primary:disabled { opacity: .5; cursor: not-allowed; }
.primary[aria-busy=true]::before { content: ''; width: 14px; height: 14px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); animation: generator-spin .7s linear infinite; }
@keyframes generator-spin { to { transform: rotate(360deg); } }
.muted { color: var(--muted); }
.error { color: var(--danger); font-size: .85em; overflow-wrap: anywhere; }
:is(button,input,select):focus-visible, .result-buttons :deep(button.copy:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.field input[type="range"] {
  --fill: 0%;
  width: 100%;
  height: 20px;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  appearance: none;
  cursor: pointer;
}
.field input[type="range"]::-webkit-slider-runnable-track {
  height: 6px;
  border-radius: var(--radius-full);
  background: linear-gradient(to right, var(--accent) var(--fill), var(--border) var(--fill));
}
.field input[type="range"]::-moz-range-track {
  height: 6px;
  border-radius: var(--radius-full);
  background: linear-gradient(to right, var(--accent) var(--fill), var(--border) var(--fill));
}
.field input[type="range"]::-webkit-slider-thumb {
  width: 18px;
  height: 18px;
  margin-top: -6px;
  border: 2px solid var(--accent);
  border-radius: var(--radius-full);
  background: var(--surface);
  appearance: none;
}
.field input[type="range"]::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: 2px solid var(--accent);
  border-radius: var(--radius-full);
  background: var(--surface);
}
.field input[type="range"]:focus-visible { outline: none; }
.field input[type="range"]:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 30%, transparent); }

@media (max-width: 1050px) and (min-width: 768px) {
  .generator-workspace { grid-template-columns: minmax(0, 1fr) 250px; }
  .type-picker { padding: 20px 18px 0; }
  .desktop-types :deep(.segmented) { flex-wrap: wrap; border-radius: var(--radius-lg); overflow-x: visible; }
  .result-panel { padding-inline: 18px; }
  .options-panel { padding-inline: 14px; }
  .generate-footer { margin-inline: 18px; flex-wrap: wrap; }
}
@media (max-width: 767px) {
  .generator :deep(.page-column) { padding: 20px 16px 12px; }
  .generator :deep(.page-head) { margin-bottom: 20px; }
  .generator-workspace { display: flex; flex-direction: column; border: 0; border-radius: 0; }
  .type-picker { flex-shrink: 0; padding: 0; }
  .desktop-types { display: none; }
  .mobile-type { display: grid; gap: 7px; color: var(--muted); font-size: .8em; }
  .mobile-type select { color: var(--text); min-height: 44px; }
  .work-scroll { display: block; flex: 1; min-height: 0; overflow-y: auto; padding-top: 24px; }
  .result-panel { padding: 0; overflow: visible; }
  .intro { margin-bottom: 18px; }
  .value-panel { padding: 18px 16px; }
  .value { font-size: 1.15em; letter-spacing: 0; min-height: 36px; }
  .result-actions { flex-direction: column; align-items: stretch; gap: 16px; }
  .result-buttons { width: 100%; }
  .reveal, .result-buttons :deep(button.copy) { flex: 1; min-height: 44px; }
  .options-panel { padding: 0; border-left: 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: var(--bg); margin-top: 24px; overflow: visible; }
  .desktop-options-heading { display: none; }
  .options-disclosure { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; min-height: 56px; padding: 8px 0; border: 0; background: transparent; color: var(--text); font: inherit; font-size: .85em; text-align: left; cursor: pointer; }
  .options-summary { display: flex; align-items: center; justify-content: flex-end; gap: 6px; color: var(--muted); font-size: .85em; text-align: right; }
  .options-summary svg { width: 14px; height: 14px; }
  .options-body { padding: 10px 0 20px; }
  .options-panel:not(.expanded) .options-body { display: none; }
  .field input:not([type=range]), .field select { min-height: 44px; }
  .options-body :deep(.toggle) { min-height: 44px; }
  .generate-footer { margin: 16px 0 0; padding-top: 14px; flex-shrink: 0; flex-direction: column; align-items: stretch; gap: 12px; }
  .generate-footer p { text-align: center; font-size: .73em; }
  .generate-footer .primary { order: -1; width: 100%; }
}
</style>
