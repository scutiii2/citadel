import { defineStore } from "pinia";
import { ref, watch } from "vue";
import {
  calendarClient,
  type AlarmChannel,
  type AlarmRule,
  type CalendarEvent,
  type CalendarFeed,
  type ChannelSwitches,
  type FeedInput,
  type FeedProblem,
} from "../api/CalendarClient";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";

/** The signed-in account's calendar: its feeds, alert rules and the admin's channel switches.
 * Answers that arrive after the account changed are dropped. */
export const useCalendarStore = defineStore("calendar", () => {
  const auth = useAuthStore();

  const feeds = ref<CalendarFeed[]>([]);
  const rules = ref<AlarmRule[]>([]);
  const switches = ref<ChannelSwitches>({ inapp: true, email: true, push: true });
  const problems = ref<FeedProblem[]>([]);
  const error = ref("");
  const ready = ref(false);
  let generation = 0;

  watch(
    () => auth.account?.id ?? null,
    () => {
      generation += 1;
      feeds.value = [];
      rules.value = [];
      problems.value = [];
      error.value = "";
      ready.value = false;
    },
    { immediate: true },
  );

  async function loadSetup(): Promise<void> {
    const started = generation;
    try {
      const [loadedFeeds, loadedRules, prefs, loadedSwitches] = await Promise.all([
        calendarClient.feeds(), calendarClient.alarms(), calendarClient.prefs(), calendarClient.channelSwitches(),
      ]);
      if (started !== generation) return;
      feeds.value = loadedFeeds;
      rules.value = loadedRules;
      switches.value = loadedSwitches;
      const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (!prefs.saved && zone) await calendarClient.setTimezone(zone).catch(() => undefined);
    } catch (err) {
      if (started === generation) error.value = errorMessage(err);
    } finally {
      if (started === generation) ready.value = true;
    }
  }

  async function loadEvents(from: Date, to: Date): Promise<CalendarEvent[]> {
    const started = generation;
    const reply = await calendarClient.events(from, to);
    if (started !== generation) return [];
    problems.value = reply.errors;
    return reply.events;
  }

  async function addFeed(input: FeedInput): Promise<void> {
    feeds.value = [...feeds.value, await calendarClient.addFeed(input)];
  }

  async function updateFeed(id: string, patch: Partial<FeedInput> & { enabled?: boolean }): Promise<void> {
    const updated = await calendarClient.updateFeed(id, patch);
    feeds.value = feeds.value.map((f) => (f.id === id ? updated : f));
  }

  async function removeFeed(id: string): Promise<void> {
    await calendarClient.removeFeed(id);
    feeds.value = feeds.value.filter((f) => f.id !== id);
  }

  async function addRule(channel: AlarmChannel, lead: number): Promise<void> {
    rules.value = [...rules.value, await calendarClient.addAlarm(channel, lead)].sort((a, b) => a.lead_minutes - b.lead_minutes);
  }

  async function updateRule(id: string, patch: Partial<Pick<AlarmRule, "channel" | "lead_minutes" | "enabled">>): Promise<void> {
    const updated = await calendarClient.updateAlarm(id, patch);
    rules.value = rules.value.map((r) => (r.id === id ? updated : r));
  }

  async function removeRule(id: string): Promise<void> {
    await calendarClient.removeAlarm(id);
    rules.value = rules.value.filter((r) => r.id !== id);
  }

  return { feeds, rules, switches, problems, error, ready, loadSetup, loadEvents, addFeed, updateFeed, removeFeed, addRule, updateRule, removeRule };
});

export type { CalendarEvent } from "../api/CalendarClient";
