<script setup lang="ts">
import type { CalendarOptions, EventClickArg, EventInput } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import FullCalendar from "@fullcalendar/vue3";
import { onBeforeUnmount, onMounted, ref } from "vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import "../../components/layout/infoPage.css";
import AlertRulesPanel from "./components/AlertRulesPanel.vue";
import EventDialog from "./components/EventDialog.vue";
import FeedsPanel from "./components/FeedsPanel.vue";
import { useCalendarStore, type CalendarEvent } from "./stores/calendar";

/** The account's read-only schedule from its ICS links, with the alert rules beside it. */
const calendar = useCalendarStore();
const grid = ref<InstanceType<typeof FullCalendar> | null>(null);
const selected = ref<CalendarEvent | null>(null);

function toInput(e: CalendarEvent): EventInput {
  const color = e.sources[0]?.color;
  return { id: `${e.uid}|${e.start}`, title: e.title, start: e.start, end: e.end, allDay: e.all_day, backgroundColor: color, borderColor: color, extendedProps: { source: e } };
}

const options: CalendarOptions = {
  plugins: [dayGridPlugin, timeGridPlugin],
  initialView: "workWeek",
  views: { workWeek: { type: "timeGridWeek", weekends: false } },
  headerToolbar: { left: "today prev,next", center: "title", right: "timeGridDay,workWeek,timeGridWeek,dayGridMonth" },
  buttonText: { today: "Today", timeGridDay: "Day", workWeek: "Work week", timeGridWeek: "Week", dayGridMonth: "Month" },
  firstDay: 1,
  height: "100%",
  nowIndicator: true,
  slotDuration: "00:30:00",
  allDaySlot: true,
  eventDidMount: (info) => info.el.style.setProperty("--event-color", info.event.backgroundColor || "var(--accent)"),
  events: (info, success, failure) => {
    calendar.loadEvents(info.start, info.end).then((list) => success(list.map(toInput)), failure);
  },
  eventClick: (arg: EventClickArg) => {
    selected.value = arg.event.extendedProps.source as CalendarEvent;
  },
};

const refetch = () => grid.value?.getApi().refetchEvents();
let timer: ReturnType<typeof setInterval> | undefined;
const onVisible = () => { if (!document.hidden) refetch(); };

onMounted(() => {
  void calendar.loadSetup();
  timer = setInterval(refetch, 5 * 60_000);
  document.addEventListener("visibilitychange", onVisible);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  document.removeEventListener("visibilitychange", onVisible);
});
</script>

<template>
  <PageLayout title="Calendar" description="Your read-only schedule from ICS links, with alerts before events." class="calendar info-content" wide fill>
    <p v-if="calendar.error" class="problem" role="alert">{{ calendar.error }}</p>
    <div class="workspace">
      <aside class="side" aria-label="Calendar settings">
        <FeedsPanel @changed="refetch" />
        <AlertRulesPanel />
      </aside>
      <section class="grid" aria-label="Schedule">
        <ul v-if="calendar.problems.length" class="issues" role="status">
          <li v-for="p in calendar.problems" :key="p.feed">⚠ {{ p.feed }}: {{ p.message }}</li>
        </ul>
        <FullCalendar ref="grid" :options="options" class="fc-host" />
      </section>
    </div>
    <EventDialog :event="selected" @close="selected = null" />
  </PageLayout>
</template>

<style scoped>
.workspace { display: grid; grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); gap: 16px; min-height: 0; flex: 1; }
.side { display: grid; align-content: start; gap: 12px; min-height: 0; overflow: auto; }
.grid { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.fc-host { flex: 1; min-height: 520px; }
.issues { margin: 0 0 8px; padding: 8px 12px; list-style: none; color: var(--warning); border: 1px solid var(--border); border-radius: var(--radius-md); font-size: 0.85rem; }
.problem { color: var(--danger); }
@media (max-width: 767px) {
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .side { overflow: visible; }
}
.calendar :deep(.fc) {
  --fc-border-color: var(--border);
  --fc-page-bg-color: var(--bg);
  --fc-neutral-bg-color: var(--surface);
  --fc-today-bg-color: color-mix(in srgb, var(--accent) 8%, transparent);
  --fc-now-indicator-color: var(--accent);
  --fc-event-border-color: transparent;
  color: var(--text);
}
.calendar :deep(.fc .fc-button) { color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: none; text-transform: none; }
.calendar :deep(.fc .fc-button-active), .calendar :deep(.fc .fc-button:hover) { color: var(--accent-contrast); background: var(--accent); border-color: var(--accent); }
.calendar :deep(.fc .fc-event) {
  color: var(--text);
  background: color-mix(in srgb, var(--event-color, var(--accent)) 18%, var(--bg));
  border: 0;
  border-left: 4px solid var(--event-color, var(--accent));
  border-radius: var(--radius-sm);
}
.calendar :deep(.fc .fc-col-header-cell-cushion), .calendar :deep(.fc .fc-daygrid-day-number), .calendar :deep(.fc .fc-timegrid-slot-label-cushion) { color: var(--muted); text-decoration: none; }
</style>
