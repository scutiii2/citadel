<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { settingsClient, type AppSettings } from "../../api/SettingsClient";
import { errorMessage } from "../../utils/errors";
import ToggleSwitch from "../ToggleSwitch.vue";
import "./admin.css";

type ChannelKey = "calendar_inapp" | "calendar_email" | "calendar_push";
const CHANNELS: { key: ChannelKey; label: string; help: string }[] = [
  { key: "calendar_inapp", label: "In-app alerts", help: "A banner and desktop notification while Ember is open." },
  { key: "calendar_email", label: "Email alerts", help: "Sent through the Email capability; it must be online." },
  { key: "calendar_push", label: "Push alerts", help: "Browser push, works with Ember closed. Needs HTTPS." },
];

const stored = ref<Pick<AppSettings, ChannelKey> | null>(null);
const draft = ref<Record<ChannelKey, boolean>>({ calendar_inapp: true, calendar_email: true, calendar_push: true });
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);

const changed = computed(() => (stored.value ? CHANNELS.filter((c) => draft.value[c.key] !== stored.value![c.key]) : []));

function adopt(settings: AppSettings): void {
  stored.value = { calendar_inapp: settings.calendar_inapp, calendar_email: settings.calendar_email, calendar_push: settings.calendar_push };
  draft.value = { ...stored.value };
}

async function load(): Promise<void> {
  loadError.value = "";
  try {
    adopt(await settingsClient.get());
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

function cancel(): void {
  if (stored.value) draft.value = { ...stored.value };
  saveError.value = "";
}

async function save(): Promise<void> {
  saveError.value = "";
  saving.value = true;
  try {
    for (const channel of changed.value) await settingsClient.set(channel.key, draft.value[channel.key]);
    stored.value = { ...draft.value };
    saved.value = true;
  } catch (err) {
    saveError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="admin-panel">
    <p v-if="loadError" class="error">error: {{ loadError }}</p>
    <section class="card">
      <div class="head"><h3>Calendar alerts</h3></div>
      <p class="muted">Which ways calendar alerts may reach people. Switching one off stops it for every account.</p>
      <div v-for="channel in CHANNELS" :key="channel.key" class="row">
        <ToggleSwitch :checked="draft[channel.key]" :aria-label="channel.label" :disabled="saving || !stored" @change="draft[channel.key] = ($event.target as HTMLInputElement).checked; saved = false">{{ channel.label }}</ToggleSwitch>
        <p class="muted">{{ channel.help }}</p>
      </div>
      <div v-if="changed.length" class="bar" role="status">
        <span>Unsaved: {{ changed.map((c) => c.label).join(", ") }}. Applies to every account.</span>
        <button type="button" class="cancel" :disabled="saving" @click="cancel">Cancel</button>
        <button type="button" class="save primary" :disabled="saving" :aria-busy="saving" @click="save">Save</button>
      </div>
      <button v-else type="button" class="save" disabled>Save</button>
      <p v-if="saveError" class="error" role="alert">error: {{ saveError }}</p>
      <p v-else-if="saved && !changed.length" class="muted" role="status">Saved.</p>
    </section>
  </div>
</template>
