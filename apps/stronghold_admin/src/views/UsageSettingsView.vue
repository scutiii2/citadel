<script setup lang="ts">
import FieldLabel from "../components/admin/FieldLabel.vue";
import ActionMessage from "../components/admin/ActionMessage.vue";
import { computed, onMounted, ref } from "vue";
import { usageSettingsClient, type UsageLimits, type UsageSettings, type UsageSettingsChanges } from "../api/UsageSettingsClient";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import { errorMessage } from "../utils/errors";

/** The token limits every account gets and the price of each model (USD per 1,000,000 tokens). Saved in Stronghold's
 * database; Stronghold uses a change for the next question and the next cost estimate, with no restart. */
interface LimitField { key: keyof UsageLimits; label: string; help?: string; step?: string }
interface PriceRow { key: number; model: string; input: string; output: string }

const LIMITS: LimitField[] = [
  { key: "six_hour_token_limit", label: "Tokens per account in 6 hours", help: "0 = unlimited." },
  { key: "weekly_token_limit", label: "Tokens per account in a week", help: "0 = unlimited." },
  { key: "max_context_tokens_per_chat", label: "Longest chat context (tokens)", help: "A chat is summarized before it passes this. 0 = no cap." },
  { key: "auto_summarize_ratio", label: "Summarize at this share of the context (0 to 1)", step: "0.05" },
];

let nextKey = 0;
const saved = ref<UsageSettings | null>(null);
const limits = ref<Record<string, string>>({});
const prices = ref<PriceRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();

function apply(view: UsageSettings) {
  saved.value = view;
  limits.value = Object.fromEntries(LIMITS.map((field) => [field.key, String(view.usage[field.key])]));
  prices.value = Object.entries(view.pricing.models).map(([model, price]) => ({
    key: nextKey++, model, input: String(price.input), output: String(price.output),
  }));
}

onMounted(async () => {
  try {
    apply(await usageSettingsClient.get());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

const limitsChanged = computed(() => !!saved.value && LIMITS.some((field) => String(limits.value[field.key] ?? "").trim() !== String(saved.value!.usage[field.key])));
const pricesChanged = computed(() => {
  if (!saved.value) return false;
  const current = Object.entries(saved.value.pricing.models);
  if (current.length !== prices.value.length) return true;
  return prices.value.some((row, index) => {
    const [model, price] = current[index];
    return row.model.trim() !== model || String(row.input).trim() !== String(price.input) || String(row.output).trim() !== String(price.output);
  });
});
const names = computed(() => prices.value.map((row) => row.model.trim().toLowerCase()));
const problem = computed(() => {
  if (prices.value.some((row) => !row.model.trim())) return "Every price needs a model name.";
  if (new Set(names.value).size !== names.value.length) return "Model names must be different.";
  if (prices.value.some((row) => String(row.input).trim() === "" || String(row.output).trim() === "")) return "Every price needs an input and an output value.";
  return "";
});
const dirty = computed(() => !!saved.value && (limitsChanged.value || pricesChanged.value));

function addPrice() {
  prices.value.push({ key: nextKey++, model: "", input: "", output: "" });
}

function removePrice(key: number) {
  prices.value = prices.value.filter((row) => row.key !== key);
}

async function save() {
  if (!dirty.value || saving.value) return;
  error.value = notice.value = "";
  if (problem.value) { error.value = problem.value; return; }
  const changes: UsageSettingsChanges = {};
  if (limitsChanged.value) {
    changes.usage = Object.fromEntries(LIMITS.map((field) => [field.key, Number(limits.value[field.key])])) as Partial<UsageLimits>;
  }
  if (pricesChanged.value) {
    changes.pricing = { models: Object.fromEntries(prices.value.map((row) => [row.model.trim(), { input: Number(row.input), output: Number(row.output) }])) };
  }
  saving.value = true;
  await panel.value?.keepFocus(async () => {
    try {
      apply(await usageSettingsClient.save(changes));
      notice.value = "Saved. Stronghold uses it from the next question.";
    } catch (err) {
      error.value = errorMessage(err);
    } finally {
      saving.value = false;
    }
  });
}

function discard() {
  if (saved.value) apply(saved.value);
  error.value = notice.value = "";
}
</script>

<template>
  <SettingsPanel ref="panel" v-model:search="search" title="Usage settings" heading="Limits and prices" label="usage settings" :dirty="dirty" :saving="saving" @save="save" @discard="discard">
    <template #help>
      <p>The token limits every account gets and what each model costs. Stronghold is the only owner of both.</p>
      <p>Prices are USD per 1,000,000 tokens; a model that is not listed has no cost estimate. Stronghold uses a change from the next question, with no restart.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <ActionMessage v-if="error" kind="error" :text="error" class="note" />
      <p v-if="notice" class="note muted" role="status" data-test="notice">{{ notice }}</p>
      <p v-if="problem && dirty" class="note muted" data-test="problem">{{ problem }}</p>
      <section v-show="panel?.matches('Limits', ...LIMITS.map((field) => field.label))" class="group" aria-labelledby="limits-title">
        <h3 id="limits-title">Limits</h3>
        <p class="help">How many tokens an account may use, and when a long chat is summarized.</p>
        <div v-for="field in LIMITS" v-show="panel?.matches('Limits', field.label)" :key="field.key" class="field">
          <FieldLabel v-if="field.help" :title="field.label" :for="`l-${field.key}`">{{ field.help }}</FieldLabel>
          <label v-else :for="`l-${field.key}`">{{ field.label }}</label>
          <input :id="`l-${field.key}`" v-model="limits[field.key]" type="number" min="0" :step="field.step ?? '1'" :disabled="saving" :data-test="field.key" />
        </div>
      </section>

      <section v-show="panel?.matches('Prices', 'Model', ...prices.map((row) => row.model))" class="group" aria-labelledby="prices-title">
        <h3 id="prices-title">Prices</h3>
        <p class="help">US dollars per 1,000,000 tokens. A model that is not listed has no cost estimate.</p>
        <div v-if="prices.length" class="price price-head" aria-hidden="true"><span>Model</span><span>Input</span><span>Output</span><span></span></div>
        <div v-for="row in prices" :key="row.key" class="price" data-test="price">
          <input v-model="row.model" aria-label="Model name" placeholder="Model name" autocomplete="off" spellcheck="false" :disabled="saving" data-test="price-model" />
          <input v-model="row.input" aria-label="Input price" type="number" min="0" step="any" placeholder="Input" :disabled="saving" data-test="price-input" />
          <input v-model="row.output" aria-label="Output price" type="number" min="0" step="any" placeholder="Output" :disabled="saving" data-test="price-output" />
          <button type="button" class="admin-icon" title="Remove model" aria-label="Remove model" :disabled="saving" data-test="price-remove" @click="removePrice(row.key)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13" /></svg>
          </button>
        </div>
        <div class="add">
          <button type="button" class="admin-icon" title="Add a model" aria-label="Add a model" :disabled="saving" data-test="price-add" @click="addPrice">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>
      </section>
    </form>
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.error { color: var(--danger); }
.muted { color: var(--muted); }
.form { display: grid; }
.group { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px 20px; align-content: start; padding: 20px 16px; }
.group > h3, .group > .help, .group > .path, .group > .price, .group > .price-head, .group > .add { grid-column: 1 / -1; }
.group > h3 { padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.field > input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.group + .group { border-top: 1px solid var(--border); }
.group h3 { margin: 0; font-size: 1em; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .price > input { min-width: 0; min-height: 44px; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.price { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.price-head { font-size: 0.8em; font-weight: 600; color: var(--muted); margin-bottom: -8px; }
.price-head span:last-child { width: 44px; }
@media (max-width: 560px) {
  .price { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; }
  .price > input:first-child { grid-column: 1 / -1; }
}
</style>
