<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { environmentClient, type EnvironmentChanges, type EnvironmentSetting } from "../api/EnvironmentClient";
import PageLayout from "../components/PageLayout.vue";
import PasswordInput from "../components/PasswordInput.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** The deployment values of Armory (addresses, link keys, Obsidian, folders). Saved in Armory's database, so a change
 * needs no file edit. A value marked "after restart" is saved at once and used from Armory's next start. A secret is
 * write-only: the page only says whether one is set. */
const settings = ref<EnvironmentSetting[]>([]);
/** What the admin typed, by field; a field absent here is unchanged. */
const edits = ref<Record<string, string | boolean>>({});
const resets = ref<Set<string>>(new Set());
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const groups = computed(() => {
  const byGroup = new Map<string, EnvironmentSetting[]>();
  for (const setting of settings.value) byGroup.set(setting.group, [...(byGroup.get(setting.group) ?? []), setting]);
  return [...byGroup.entries()];
});
const changed = computed(() => Object.keys(edits.value).length > 0 || resets.value.size > 0);

function text(setting: EnvironmentSetting): string {
  const edit = edits.value[setting.field];
  return typeof edit === "string" ? edit : setting.secret ? "" : String(setting.value ?? "");
}

function flag(setting: EnvironmentSetting): boolean {
  const edit = edits.value[setting.field];
  return typeof edit === "boolean" ? edit : setting.value === true;
}

function edit(setting: EnvironmentSetting, value: string | boolean) {
  resets.value.delete(setting.field);
  const same = setting.secret ? value === "" : value === (setting.kind === "bool" ? setting.value === true : String(setting.value ?? ""));
  if (same) delete edits.value[setting.field];
  else edits.value[setting.field] = value;
}

function reset(setting: EnvironmentSetting) {
  delete edits.value[setting.field];
  resets.value.add(setting.field);
}

function pending(setting: EnvironmentSetting): boolean {
  return setting.field in edits.value || resets.value.has(setting.field);
}

function apply(view: { settings: EnvironmentSetting[] }) {
  settings.value = view.settings;
  edits.value = {};
  resets.value = new Set();
}

onMounted(async () => {
  try {
    apply(await environmentClient.get());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

async function save() {
  const changes: EnvironmentChanges = {};
  for (const setting of settings.value) {
    const value = edits.value[setting.field];
    if (resets.value.has(setting.field)) changes[setting.field] = null;
    else if (value !== undefined) changes[setting.field] = setting.kind === "number" && typeof value === "string" ? Number(value) : value;
  }
  saving.value = true;
  error.value = notice.value = "";
  try {
    const view = await environmentClient.save(changes);
    apply(view);
    const later = (view.restart ?? []).map((field) => settings.value.find((s) => s.field === field)?.label ?? field);
    notice.value = later.length ? `Saved. Used after Armory restarts: ${later.join(", ")}.` : "Saved. Armory uses it now.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <PageLayout
    class="info-content environment"
    title="Settings"
    description="Addresses, link signing keys, Obsidian and folders. They are saved in Armory's database. A value you have not set here comes from Armory's .env file or its default."
  >
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <section v-for="[group, rows] in groups" :key="group" class="card" :aria-labelledby="`g-${group}`">
        <h2 :id="`g-${group}`" class="title">{{ group }}</h2>
        <div v-for="setting in rows" :key="setting.field" class="field" :data-test="`row-${setting.field}`">
          <label :for="`f-${setting.field}`">
            {{ setting.label }}
            <span v-if="setting.restart" class="tag">after restart</span>
            <span v-if="setting.stored || resets.has(setting.field)" class="tag" :class="{ gone: resets.has(setting.field) }">
              {{ resets.has(setting.field) ? "back to default" : "set here" }}
            </span>
          </label>
          <label v-if="setting.kind === 'bool'" class="check">
            <input
              :id="`f-${setting.field}`"
              type="checkbox"
              :checked="flag(setting)"
              :disabled="saving"
              data-test="input"
              @change="edit(setting, ($event.target as HTMLInputElement).checked)"
            />
            {{ flag(setting) ? "On" : "Off" }}
          </label>
          <PasswordInput
            v-else-if="setting.secret"
            :model-value="text(setting)"
            :label="''"
            autocomplete="off"
            data-test="input"
            :disabled="saving"
            :placeholder="setting.has_value ? 'A value is set. Type to replace it.' : 'Not set'"
            @update:model-value="edit(setting, $event)"
          />
          <input
            v-else
            :id="`f-${setting.field}`"
            :value="text(setting)"
            :type="setting.kind === 'url' ? 'url' : setting.kind === 'number' ? 'number' : 'text'"
            :disabled="saving"
            autocomplete="off"
            spellcheck="false"
            data-test="input"
            @input="edit(setting, ($event.target as HTMLInputElement).value)"
          />
          <p v-if="setting.help" class="help">{{ setting.help }}</p>
          <div v-if="setting.stored && !pending(setting)" class="inline">
            <button type="button" class="chip" :disabled="saving" data-test="reset" @click="reset(setting)">Use the default</button>
          </div>
        </div>
      </section>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="saving || !changed">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </PageLayout>
</template>

<style scoped>
.form { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 16px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label:first-child { font-size: 0.9em; font-weight: 600; }
.field > input[type="url"], .field > input[type="text"], .field > input[type="number"] { min-width: 0; min-height: 44px; width: 100%; }
.check { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; }
.tag { margin-left: 8px; padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; font-weight: 400; color: var(--muted); }
.tag.gone { border-color: var(--accent); color: var(--text); }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.inline { display: flex; }
.actions { display: flex; justify-content: flex-end; }
</style>
