<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { McpServerClient } from "../api/McpServerClient";
import CopyButton from "../components/CopyButton.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

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
let sequence = 0;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

const live = computed(() => tab.value === "password" || tab.value === "passphrase" || tab.value === "pin");
const result = computed(() => results[tab.value]);
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
/** A TOTP code is shown in groups of three, like an authenticator app. */
const shown = computed(() => {
  const r = result.value;
  if (!r) return "";
  if (tab.value === "totp") return r.value.replace(/(\d{3})(?=\d)/g, "$1 ");
  return revealed.value || tab.value !== "totp-secret" ? r.value : "•".repeat(Math.min(r.value.length, 32));
});

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

// The live tabs make a new value whenever an option changes.
watch(
  () => [options.password, options.passphrase, options.pin, tab.value] as const,
  () => {
    if (live.value && (tab.value !== "password" || characterTypes.value)) void run();
  },
  { deep: true },
);
watch(tab, () => {
  revealed.value = false;
  error.value = "";
  // Leaving the TOTP code tab stops its refresh; coming back runs it again.
  if (tab.value !== "totp") clearTimer();
  else if (options.totp.secret.trim() !== "" && results.totp) void run("totp");
});

onMounted(() => void run());
onBeforeUnmount(() => {
  sequence++;
  clearTimer();
});
</script>

<template>
  <section class="info-page generator">
    <div class="page-column">
      <header class="top">
        <div>
          <h2 class="page-title">Generator</h2>
          <p class="page-description">Random passwords, passphrases, PINs and TOTP codes. Nothing is stored; a value is shown once.</p>
        </div>
      </header>

      <SegmentedControl v-model="tab" aria-label="Generator type" :options="TABS" />

      <article class="card panel">
        <form class="options" @submit.prevent="canRun && run()">
          <template v-if="tab === 'password'">
            <label class="field">Length: {{ options.password.length }}
              <input v-model.number="options.password.length" type="range" min="8" max="128" />
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
              <input v-model.number="options.passphrase.words" type="range" min="3" max="12" />
            </label>
            <label class="field">Separator
              <input v-model="options.passphrase.separator" type="text" maxlength="3" aria-label="Separator" />
            </label>
            <ToggleSwitch small :checked="options.passphrase.capitalize" @change="options.passphrase.capitalize = checked($event)">Capitalise each word</ToggleSwitch>
            <ToggleSwitch small :checked="options.passphrase.add_number" @change="options.passphrase.add_number = checked($event)">Add a digit</ToggleSwitch>
          </template>
          <template v-else-if="tab === 'pin'">
            <label class="field">Digits: {{ options.pin.length }}
              <input v-model.number="options.pin.length" type="range" min="4" max="12" />
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
          <div class="actions">
            <button type="submit" class="primary" :disabled="!canRun">
              {{ tab === "totp" ? "Show code" : live && result ? "Regenerate" : "Generate" }}
            </button>
          </div>
        </form>

        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div v-else-if="result" class="result" aria-live="polite">
          <div class="value-row">
            <code class="value" :class="{ code: tab === 'totp' }" data-testid="generated-value">{{ shown }}</code>
            <button v-if="tab === 'totp-secret'" type="button" class="chip" @click="revealed = !revealed">
              {{ revealed ? "Hide" : "Show" }}
            </button>
            <CopyButton :text="result.value" label="Copy value" />
          </div>
          <div v-if="result.bits !== null" class="strength" role="meter" aria-label="Strength" :aria-valuenow="Math.round(result.bits)" aria-valuemin="0" :aria-valuemax="FULL_BITS">
            <span class="bar"><span class="fill" :style="{ width: `${strength}%` }" /></span>
            <span class="muted">{{ Math.round(result.bits) }} bits</span>
          </div>
          <p v-if="result.remaining !== null" class="muted">Changes in about {{ result.remaining }} s.</p>
          <p v-if="result.detail" class="muted">{{ result.detail }}</p>
        </div>
        <p v-else-if="busy" class="muted" role="status">Generating…</p>
      </article>

      <p class="muted note">Nothing here is stored. A generated value travels through the chat like any tool result.</p>
    </div>
  </section>
</template>

<style scoped>
.panel { margin-top: 14px; }
.options { display: grid; gap: 10px; }
.field { display: grid; gap: 4px; font-size: 0.9em; }
.actions { display: flex; gap: 8px; }
.result { display: grid; gap: 8px; margin-top: 14px; }
.value-row { display: flex; align-items: center; gap: 8px; }
.value {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--code-bg);
  font-family: var(--mono);
  overflow-wrap: anywhere;
}
.value.code { font-size: 1.6em; letter-spacing: 0.08em; }
.strength { display: flex; align-items: center; gap: 10px; }
.bar { flex: 1; height: 6px; border-radius: var(--radius-full); background: var(--border); overflow: hidden; }
.fill { display: block; height: 100%; background: var(--accent); transition: width 0.2s; }
.note { margin-top: 12px; font-size: 0.85em; }
.muted { color: var(--muted); }
.error { color: var(--danger); }
</style>
