import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { calendarClient, type CalendarAlert } from "../api/CalendarClient";

const INTERVAL_MS = 30_000;
// An alert for an event that began more than this long ago is no use any more.
const STALE_MS = 30 * 60_000;

/** Polls the in-app alert inbox while a signed-in account that may use the calendar has Ember open.
 * Each new alert also raises a desktop notification when the browser allows it. */
export function useAlertPoller() {
  const auth = useAuthStore();
  const alerts = ref<CalendarAlert[]>([]);
  const notified = new Set<string>();
  let timer: ReturnType<typeof setInterval> | undefined;
  let generation = 0;

  const active = computed(() => auth.account !== null && !auth.needsVerification && auth.hasPermission("calendar.use"));

  function notify(alert: CalendarAlert): void {
    if (notified.has(alert.id)) return;
    notified.add(alert.id);
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    try {
      new Notification(alert.title, { body: `Starts at ${new Date(alert.start_utc).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`, tag: `ember-calendar-${alert.id}` });
    } catch {
      // The in-page toast still shows.
    }
  }

  async function poll(): Promise<void> {
    if (!active.value) return;
    const started = generation;
    try {
      const fresh = (await calendarClient.unseenAlerts()).filter((a) => Date.now() - new Date(a.start_utc).getTime() < STALE_MS);
      if (started !== generation) return;
      fresh.forEach(notify);
      alerts.value = fresh;
    } catch {
      // A failed poll is retried on the next tick; an alert is never lost, it stays unseen on the server.
    }
  }

  async function dismiss(id: string): Promise<void> {
    alerts.value = alerts.value.filter((a) => a.id !== id);
    await calendarClient.markSeen(id).catch(() => undefined);
  }

  const onVisible = () => { if (!document.hidden) void poll(); };

  watch(
    active,
    (on) => {
      generation += 1;
      clearInterval(timer);
      alerts.value = [];
      if (on) {
        void poll();
        timer = setInterval(() => void poll(), INTERVAL_MS);
      }
    },
    { immediate: true },
  );
  document.addEventListener("visibilitychange", onVisible);
  onBeforeUnmount(() => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
  });

  return { alerts, dismiss, poll };
}
