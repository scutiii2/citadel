<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { usageSettingsClient, type UsageLimits, type UsageSettings, type UsageSettingsChanges } from "../api/UsageSettingsClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

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
const canSave = computed(() => (limitsChanged.value || pricesChanged.value) && !problem.value);

function addPrice() {
  prices.value.push({ key: nextKey++, model: "", input: "", output: "" });
}

function removePrice(key: number) {
  prices.value = prices.value.filter((row) => row.key !== key);
}

async function save() {
  const changes: UsageSettingsChanges = {};
  if (limitsChanged.value) {
    changes.usage = Object.fromEntries(LIMITS.map((field) => [field.key, Number(limits.value[field.key])])) as Partial<UsageLimits>;
  }
  if (pricesChanged.value) {
    changes.pricing = { models: Object.fromEntries(prices.value.map((row) => [row.model.trim(), { input: Number(row.input), output: Number(row.output) }])) };
  }
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await usageSettingsClient.save(changes));
    notice.value = "Saved. Stronghold uses it from the next question.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageLayout
    class="info-content usage-settings"
    title="Usage settings"
    description="The token limits every account gets and what each model costs. Stronghold is the only owner of both."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <section class="card" aria-labelledby="limits-title">
        <h2 id="limits-title" class="title">Limits</h2>
        <div v-for="field in LIMITS" :key="field.key" class="field">
          <label :for="`l-${field.key}`">{{ field.label }}</label>
          <input :id="`l-${field.key}`" v-model="limits[field.key]" type="number" min="0" :step="field.step ?? '1'" :disabled="saving" :data-test="field.key" />
          <p v-if="field.help" class="help">{{ field.help }}</p>
        </div>
      </section>

      <section class="card" aria-labelledby="prices-title">
        <h2 id="prices-title" class="title">Prices</h2>
        <p class="help">USD per 1,000,000 tokens. A model that is not listed has no cost estimate.</p>
        <div v-for="row in prices" :key="row.key" class="price" data-test="price">
          <input v-model="row.model" aria-label="Model name" placeholder="Model name" autocomplete="off" spellcheck="false" :disabled="saving" data-test="price-model" />
          <input v-model="row.input" aria-label="Input price" type="number" min="0" step="any" placeholder="Input" :disabled="saving" data-test="price-input" />
          <input v-model="row.output" aria-label="Output price" type="number" min="0" step="any" placeholder="Output" :disabled="saving" data-test="price-output" />
          <button type="button" class="chip" :disabled="saving" data-test="price-remove" @click="removePrice(row.key)">Remove</button>
        </div>
        <div><button type="button" class="chip" :disabled="saving" data-test="price-add" @click="addPrice">Add a model</button></div>
      </section>

      <p v-if="problem" class="help" data-test="problem">{{ problem }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="saving || !canSave">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </PageLayout>
</template>

<style scoped>
.form { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .price > input { min-width: 0; min-height: 44px; width: 100%; }
.price { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.actions { display: flex; justify-content: flex-end; }
@media (max-width: 560px) {
  .price { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .price > input:first-child { grid-column: 1 / -1; }
}
</style>
