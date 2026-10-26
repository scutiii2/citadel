<script setup lang="ts">
import { onMounted, ref } from "vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage } from "../../../utils/errors";
import type { AlarmChannel, AlarmRule } from "../api/CalendarClient";
import { currentPushEndpoint, disablePush, enablePush, pushSupported } from "../composables/usePushSubscription";
import { useCalendarStore } from "../stores/calendar";
import CalendarPanel from "./CalendarPanel.vue";

/** Alert rules: which way (in-app, email, push) and how long before. Each rule fires once per event. */
const calendar = useCalendarStore();

const CHANNELS: { id: AlarmChannel; label: string }[] = [
  { id: "inapp", label: "In Ember" },
  { id: "email", label: "Email" },
  { id: "push", label: "Push notification" },
];
const LEADS = [5, 10, 15, 30, 60, 120, 1440];

const channel = ref<AlarmChannel>("inapp");
const lead = ref(15);
const error = ref("");
const pushMessage = ref("");
const pushOn = ref(false);

onMounted(async () => {
  pushOn.value = (await currentPushEndpoint()) !== null;
});

function label(id: AlarmChannel): string {
  return CHANNELS.find((c) => c.id === id)?.label ?? id;
}

function leadText(minutes: number): string {
  if (minutes % 1440 === 0) return minutes === 1440 ? "1 day before" : `${minutes / 1440} days before`;
  if (minutes % 60 === 0) return minutes === 60 ? "1 hour before" : `${minutes / 60} hours before`;
  return `${minutes} minutes before`;
}

function available(id: AlarmChannel): boolean {
  return calendar.switches[id];
}

async function run(action: () => Promise<void>): Promise<void> {
  error.value = "";
  try {
    await action();
  } catch (err) {
    error.value = errorMessage(err);
  }
}

const add = () => run(() => calendar.addRule(channel.value, lead.value));
const toggle = (rule: AlarmRule) => run(() => calendar.updateRule(rule.id, { enabled: !rule.enabled }));
const retime = (rule: AlarmRule, minutes: number) => run(() => calendar.updateRule(rule.id, { lead_minutes: minutes }));
const remove = (rule: AlarmRule) => run(() => calendar.removeRule(rule.id));

async function turnPushOn(): Promise<void> {
  pushMessage.value = await enablePush();
  pushOn.value = pushMessage.value === "";
}

async function turnPushOff(): Promise<void> {
  await disablePush();
  pushOn.value = false;
}
</script>

<template>
  <CalendarPanel title="Alerts">
    <ul v-if="calendar.rules.length" class="rules" aria-label="Alert rules">
      <li v-for="rule in calendar.rules" :key="rule.id" class="rule">
        <ToggleSwitch small :checked="rule.enabled && available(rule.channel)" :disabled="!available(rule.channel)" :aria-label="`${label(rule.channel)}, ${leadText(rule.lead_minutes)}`" @change="toggle(rule)" />
        <span class="what">
          {{ label(rule.channel) }}
          <select :value="rule.lead_minutes" :aria-label="`Lead time for ${label(rule.channel)}`" @change="retime(rule, Number(($event.target as HTMLSelectElement).value))">
            <option v-for="m in LEADS" :key="m" :value="m">{{ leadText(m) }}</option>
            <option v-if="!LEADS.includes(rule.lead_minutes)" :value="rule.lead_minutes">{{ leadText(rule.lead_minutes) }}</option>
          </select>
        </span>
        <button type="button" class="chip" :aria-label="`Remove ${label(rule.channel)} alert ${leadText(rule.lead_minutes)}`" @click="remove(rule)">Remove</button>
        <p v-if="!available(rule.channel)" class="muted">Switched off by an administrator.</p>
      </li>
    </ul>
    <p v-else class="muted">No alerts. Add one below.</p>

    <form class="add" @submit.prevent="add">
      <label>Type
        <select v-model="channel">
          <option v-for="c in CHANNELS" :key="c.id" :value="c.id" :disabled="!available(c.id)">{{ c.label }}{{ available(c.id) ? "" : " (off)" }}</option>
        </select>
      </label>
      <label>When
        <select v-model.number="lead"><option v-for="m in LEADS" :key="m" :value="m">{{ leadText(m) }}</option></select>
      </label>
      <button type="submit" class="primary">Add alert</button>
    </form>
    <p v-if="error" class="problem" role="alert">{{ error }}</p>

    <div v-if="calendar.switches.push && pushSupported()" class="push">
      <span>Push on this device: <strong>{{ pushOn ? "on" : "off" }}</strong></span>
      <button v-if="!pushOn" type="button" class="chip" @click="turnPushOn">Turn on</button>
      <button v-else type="button" class="chip" @click="turnPushOff">Turn off</button>
      <p v-if="pushMessage" class="problem" role="status">{{ pushMessage }}</p>
    </div>
  </CalendarPanel>
</template>

<style scoped>
.rules { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.rule { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.rule .muted { grid-column: 1 / -1; }
.what { display: grid; gap: 4px; min-width: 0; }
select { min-height: 36px; padding: 4px 8px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; }
.add { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: end; }
.add label { display: grid; gap: 4px; font-size: 0.85rem; color: var(--muted); }
.add .primary { grid-column: 1 / -1; }
.push { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 0.9rem; }
.problem { margin: 0; font-size: 0.85rem; color: var(--danger); }
.muted { margin: 0; color: var(--muted); font-size: 0.85rem; }
</style>
