<script setup lang="ts">
import { computed, ref } from "vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage } from "../../../utils/errors";
import type { CalendarFeed } from "../api/CalendarClient";
import { nextFeedColor } from "../utils/palette";
import { useCalendarStore } from "../stores/calendar";
import CalendarPanel from "./CalendarPanel.vue";

/** Calendar links: add, show/hide, recolor, rename and remove. The link itself is never shown again after saving. */
const emit = defineEmits<{ changed: [] }>();
const calendar = useCalendarStore();

const name = ref("");
const url = ref("");
const formError = ref("");
const busy = ref(false);
const removing = ref<CalendarFeed | null>(null);
const rowError = ref("");

const color = computed(() => nextFeedColor(calendar.feeds.map((f) => f.color)));

async function add(): Promise<void> {
  formError.value = "";
  busy.value = true;
  try {
    await calendar.addFeed({ name: name.value.trim() || "Calendar", url: url.value, color: color.value });
    name.value = "";
    url.value = "";
    emit("changed");
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function change(feed: CalendarFeed, patch: { name?: string; color?: string; enabled?: boolean }): Promise<void> {
  rowError.value = "";
  try {
    await calendar.updateFeed(feed.id, patch);
    emit("changed");
  } catch (err) {
    rowError.value = errorMessage(err);
  }
}

async function remove(): Promise<void> {
  const feed = removing.value;
  if (!feed) return;
  busy.value = true;
  try {
    await calendar.removeFeed(feed.id);
    removing.value = null;
    emit("changed");
  } catch (err) {
    rowError.value = errorMessage(err);
    removing.value = null;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <CalendarPanel title="My calendars">
    <ul v-if="calendar.feeds.length" class="feeds" aria-label="Calendars">
      <li v-for="feed in calendar.feeds" :key="feed.id" class="feed">
        <ToggleSwitch small :checked="feed.enabled" :aria-label="`Show ${feed.name}`" @change="change(feed, { enabled: !feed.enabled })" />
        <input class="swatch" type="color" :value="feed.color" :aria-label="`Color of ${feed.name}`" @change="change(feed, { color: ($event.target as HTMLInputElement).value })" />
        <input class="name" type="text" :value="feed.name" maxlength="60" :aria-label="`Name of calendar ${feed.name}`" @change="change(feed, { name: ($event.target as HTMLInputElement).value })" />
        <button type="button" class="chip" :aria-label="`Remove ${feed.name}`" @click="removing = feed">Remove</button>
        <p v-if="feed.last_error" class="problem" role="status">Could not refresh: {{ feed.last_error }}</p>
      </li>
    </ul>
    <p v-else class="muted">No calendars yet. Paste a published ICS link below.</p>
    <p v-if="rowError" class="problem" role="alert">{{ rowError }}</p>

    <form class="add" @submit.prevent="add">
      <label>Label<input v-model="name" type="text" maxlength="60" autocomplete="off" placeholder="Work" /></label>
      <label>
        ICS link
        <input v-model="url" type="url" required autocomplete="off" inputmode="url" placeholder="https://… or webcal://…" :aria-invalid="formError ? 'true' : undefined" aria-describedby="feed-error" />
      </label>
      <p id="feed-error" class="problem" role="alert">{{ formError }}</p>
      <button type="submit" class="primary" :disabled="busy" :aria-busy="busy">Add calendar</button>
    </form>

    <ConfirmModal
      :open="removing !== null"
      title="Remove calendar"
      :message="`Remove ${removing?.name ?? ''}? Its events disappear from your schedule. The calendar itself is not touched.`"
      confirm-label="Remove"
      danger
      :busy="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </CalendarPanel>
</template>

<style scoped>
.feeds { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.feed { display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.feed .problem { grid-column: 1 / -1; }
.swatch { width: 28px; height: 28px; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-full); background: none; }
.name, .add input { min-width: 0; min-height: 36px; padding: 4px 8px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; }
.add { display: grid; gap: 8px; }
.add label { display: grid; gap: 4px; font-size: 0.85rem; color: var(--muted); }
.problem { margin: 0; min-height: 1em; font-size: 0.85rem; color: var(--danger); }
.muted { margin: 0; color: var(--muted); font-size: 0.9rem; }
</style>
