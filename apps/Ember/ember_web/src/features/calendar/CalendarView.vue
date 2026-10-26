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
  const state = e.cancelled ? "cancelled" : new Date(e.end) < new Date() ? "done" : "upcoming";
  return { id: `${e.uid}|${e.start}`, title: e.title, start: e.start, end: e.end, allDay: e.all_day, classNames: [`is-${state}`], extendedProps: { source: e } };
}

/** A left bar striped in each schedule's color, so a shared event shows every schedule it belongs to. */
function bar(e: CalendarEvent): string {
  const colors = e.sources.map((s) => s.color);
  const stops = colors.map((c, i) => `${c} ${(i * 100) / colors.length}% ${((i + 1) * 100) / colors.length}%`);
  return colors.length ? `linear-gradient(${stops.join(", ")})` : "var(--muted)";
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
        <FullCalendar ref="grid" :options="options" class="fc-host">
          <template #eventContent="{ event, timeText }">
            <div class="ev" :style="{ '--bar': bar(event.extendedProps.source) }">
              <span class="ev-title">{{ timeText }} {{ event.title }}</span>
              <span class="ev-sources">
                <span v-for="s in event.extendedProps.source.sources" :key="s.name" class="ev-source"><i :style="{ background: s.color }" />{{ s.name }}</span>
              </span>
            </div>
          </template>
        </FullCalendar>
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
  /* Stacked: size to the content and let the page scroll, so the grid cannot be squeezed over the panels above it. */
  .workspace { grid-template-columns: minmax(0, 1fr); flex: none; }
  .side { overflow: visible; }
  .grid { height: 36rem; }
  .calendar :deep(.fc .fc-header-toolbar) { flex-wrap: wrap; justify-content: center; gap: 8px; }
  /* Seven cells of 7.5rem so a month cell can show a title and its schedule names; the grid scrolls sideways, the toolbar stays. */
  .calendar :deep(.fc .fc-view-harness) { overflow-x: auto; }
  .calendar :deep(.fc .fc-dayGridMonth-view) { min-width: 52.5rem; }
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
  --event-color: var(--success);
  color: var(--text);
  background: color-mix(in srgb, var(--event-color) 22%, var(--bg));
  border: 0;
  border-radius: var(--radius-sm);
}
.calendar :deep(.fc .fc-event.is-done), .calendar :deep(.fc .fc-event.is-cancelled) { --event-color: var(--muted); color: var(--muted); }
.calendar :deep(.fc .fc-event.is-cancelled .ev-title) { text-decoration: line-through; }
.calendar :deep(.ev) { display: grid; gap: 2px; min-width: 0; height: 100%; padding: 1px 4px 1px 10px; position: relative; overflow: hidden; font-size: 0.8rem; }
.calendar :deep(.ev::before) { content: ""; position: absolute; inset: 0 auto 0 0; width: 5px; background: var(--bar); }
.calendar :deep(.ev-title) { overflow: hidden; text-overflow: ellipsis; font-weight: 600; }
.calendar :deep(.ev-sources) { display: flex; flex-wrap: wrap; gap: 2px 8px; font-size: 0.72rem; color: var(--muted); }
.calendar :deep(.ev-source) { display: inline-flex; align-items: center; gap: 4px; }
.calendar :deep(.ev-source i) { width: 8px; height: 8px; border-radius: var(--radius-full); flex: none; }
.calendar :deep(.fc .fc-col-header-cell-cushion), .calendar :deep(.fc .fc-daygrid-day-number), .calendar :deep(.fc .fc-timegrid-slot-label-cushion) { color: var(--muted); text-decoration: none; }
</style>
