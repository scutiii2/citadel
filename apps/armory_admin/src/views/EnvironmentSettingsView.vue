<script setup lang="ts">
import { PanelHelp } from "@citadel/ui";
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { environmentClient, type EnvironmentChanges, type EnvironmentSetting } from "../api/EnvironmentClient";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import { PasswordInput } from "@citadel/ui";
import { ToggleSwitch } from "@citadel/ui";
import { errorMessage } from "../utils/errors";

/** The deployment values of Armory (addresses, link keys, folders). Saved in Armory's database, so a change
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
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();

/** One line under each group's title. A group without an entry shows none. */
const GROUP_LEDES: Record<string, string> = {
  "PDF and video links": "The public addresses and signing keys behind the download links.",
  "Web research and scraping": "The keys and address for the web search and page scraping tools.",
  "Services Armory calls": "Which Treasury instance and connection Armory's database tools use.",
  "Folders the read-only tools look at": "Where the read-only tools may read files.",
};

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
  if (!changed.value || saving.value) return;
  const changes: EnvironmentChanges = {};
  for (const setting of settings.value) {
    const value = edits.value[setting.field];
    if (resets.value.has(setting.field)) changes[setting.field] = null;
    else if (value !== undefined) changes[setting.field] = setting.kind === "number" && typeof value === "string" ? Number(value) : value;
  }
  saving.value = true;
  error.value = notice.value = "";
  await panel.value?.keepFocus(async () => {
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
  });
}

function discard() {
  edits.value = {};
  resets.value = new Set();
  error.value = notice.value = "";
}
</script>

<template>
  <SettingsPanel ref="panel" v-model:search="search" title="Settings" heading="Deployment values" label="settings" :dirty="changed" :saving="saving" @save="save" @discard="discard">
    <template #help>
      <p>Addresses, link signing keys and folders. They are saved in Armory's database.</p>
      <p>A value you have not set here comes from Armory's .env file or its default. A value marked after restart is saved at once and used from Armory's next start.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <ActionMessage v-if="error" kind="error" :text="error" class="note" />
      <p v-if="notice" class="note muted" role="status" data-test="notice">{{ notice }}</p>
      <section v-for="[group, rows] in groups" v-show="rows.some((setting) => panel?.matches(group, setting.label, setting.field, setting.help))" :key="group" class="group fields" :aria-labelledby="`g-${group}`">
        <h3 :id="`g-${group}`">{{ group }}</h3>
        <p v-if="GROUP_LEDES[group]" class="lede">{{ GROUP_LEDES[group] }}</p>
        <div v-for="setting in rows" v-show="panel?.matches(group, setting.label, setting.field, setting.help)" :key="setting.field" class="field" :data-test="`row-${setting.field}`">
          <span class="label-line">
            <label :for="`f-${setting.field}`">
              {{ setting.label }}
              <span v-if="setting.restart" class="tag">after restart</span>
              <span v-if="setting.stored || resets.has(setting.field)" class="tag" :class="{ gone: resets.has(setting.field) }">
                {{ resets.has(setting.field) ? "back to default" : "set here" }}
              </span>
            </label>
            <PanelHelp v-if="setting.help" :title="setting.label">{{ setting.help }}</PanelHelp>
          </span>
          <ToggleSwitch
            v-if="setting.kind === 'bool'"
            :id="`f-${setting.field}`"
            :checked="flag(setting)"
            :disabled="saving"
            :aria-label="setting.label"
            data-test="input"
            @change="edit(setting, ($event.target as HTMLInputElement).checked)"
          />
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
          <div v-if="setting.stored && !pending(setting)" class="inline">
            <button type="button" class="chip" :disabled="saving" data-test="reset" @click="reset(setting)">Use the default</button>
          </div>
        </div>
      </section>
      <p v-if="groups.length && !groups.some(([group, rows]) => rows.some((setting) => panel?.matches(group, setting.label, setting.field, setting.help)))" class="note muted">No settings match your search.</p>
    </form>
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.error { color: var(--danger); }
.muted { color: var(--muted); }
.form { display: grid; }
.group { display: grid; gap: 16px; max-width: 720px; padding: 16px; }
.group + .group { border-top: 1px solid var(--border); }
.group h3 { margin: 0; font-size: 1em; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label:first-child { font-size: 0.9em; font-weight: 600; }
.field > input[type="url"], .field > input[type="text"], .field > input[type="number"] { min-width: 0; min-height: 44px; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.tag { margin-left: 8px; padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; font-weight: 400; color: var(--muted); }
.tag.gone { border-color: var(--accent); color: var(--text); }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.inline { display: flex; }
.label-line { display: flex; align-items: center; gap: 2px; min-width: 0; }
.label-line :deep(.admin-icon) { width: 28px; height: 28px; }
.label-line :deep(.admin-icon svg) { width: 15px; height: 15px; }
.group.fields { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); max-width: none; align-items: start; }
.group.fields > h3, .group.fields > .lede { grid-column: 1 / -1; }
.lede { margin: -8px 0 0; color: var(--muted); font-size: 0.9em; }
</style>
