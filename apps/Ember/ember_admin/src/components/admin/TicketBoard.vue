<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { AdminTicket, TicketGroup, TicketStatus } from "../../api/TicketsAdminClient";
import { formatTicketTime, PRIORITY_LABELS, SOURCE_LABELS, STATUS_ICONS, STATUS_LABELS } from "../../utils/ticketFormat";

const props = defineProps<{ tickets: AdminTicket[]; groups: TicketGroup[]; busy: boolean; statusFilter: "all" | TicketStatus }>();
const emit = defineEmits<{ select: [ticket: AdminTicket]; status: [ticket: AdminTicket, status: TicketStatus] }>();
const STATUSES = Object.keys(STATUS_LABELS) as TicketStatus[];
const DESCRIPTIONS: Record<TicketStatus, string> = {
  open: "Ready for triage",
  in_progress: "Being worked on",
  resolved: "Fix delivered; awaiting closure",
  closed: "Completed and archived",
};
const PRIORITY_ICONS = {
  urgent: "M12 3 2 21h20zM12 9v5M12 17h.01",
  high: "m7 14 5-5 5 5",
  normal: "M5 10h14M5 14h14",
  low: "m7 10 5 5 5-5",
};
const mobileColumn = ref<TicketStatus>("open");
watch(() => props.statusFilter, status => {
  if (status !== "all") mobileColumn.value = status;
}, { immediate: true });
const dragged = ref<AdminTicket | null>(null);
const dropTarget = ref<TicketStatus | null>(null);
const groupNames = computed(() => new Map(props.groups.map(group => [group.id, group.title])));
const columns = computed(() => STATUSES.map(status => ({ status, tickets: props.tickets.filter(ticket => ticket.status === status) })));

function startDrag(ticket: AdminTicket, event: DragEvent): void {
  if (props.busy) { event.preventDefault(); return; }
  dragged.value = ticket;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(ticket.id));
  }
}
function dragOver(status: TicketStatus, event: DragEvent): void {
  if (props.busy || !dragged.value || dragged.value.status === status) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  dropTarget.value = status;
}
function endDrag(): void {
  dragged.value = null;
  dropTarget.value = null;
}
function drop(status: TicketStatus): void {
  const ticket = dragged.value;
  endDrag();
  if (!props.busy && ticket && ticket.status !== status) emit("status", ticket, status);
}
</script>

<template>
  <div class="ticket-board">
    <label class="mobile-column-control">
      <span class="sr-only">Visible column</span>
      <select v-model="mobileColumn" aria-label="Visible column">
        <option v-for="column in columns" :key="column.status" :value="column.status">
          {{ STATUS_LABELS[column.status] }} ({{ column.tickets.length }})
        </option>
      </select>
    </label>
    <div class="kanban-board" aria-label="Tickets by status">
      <section
        v-for="column in columns" :key="column.status"
        :class="['kanban-column', column.status, { 'mobile-hidden': mobileColumn !== column.status, 'drop-target': dropTarget === column.status }]"
        :data-status="column.status" :aria-label="`${STATUS_LABELS[column.status]} tickets`"
        @dragover="dragOver(column.status, $event)" @dragleave.self="dropTarget = null" @drop.prevent="drop(column.status)"
      >
        <header class="column-head">
          <h3><svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[column.status]" /></svg>{{ STATUS_LABELS[column.status] }}</h3>
          <span class="column-count">{{ column.tickets.length }}</span>
        </header>
        <p class="column-description">{{ DESCRIPTIONS[column.status] }}</p>
        <div class="column-cards">
          <button
            v-for="ticket in column.tickets" :key="ticket.id" type="button"
            class="ticket-card" :data-ticket-id="ticket.id" :draggable="!busy" :aria-label="`Ticket ${ticket.id}: ${ticket.title}`"
            @click="emit('select', ticket)" @dragstart="startDrag(ticket, $event)" @dragend="endDrag"
          >
            <span class="card-top">
              <span class="ticket-id">#{{ ticket.id }} · {{ SOURCE_LABELS[ticket.source] }}</span>
              <span :class="['ticket-priority', ticket.effective_priority]"><svg viewBox="0 0 24 24" aria-hidden="true"><path :d="PRIORITY_ICONS[ticket.effective_priority]" /></svg>{{ PRIORITY_LABELS[ticket.effective_priority] }}</span>
            </span>
            <span class="card-title">{{ ticket.title }}</span>
            <span class="card-description">{{ ticket.description }}</span>
            <span v-if="ticket.tags.length" class="card-tags"><span v-for="tag in ticket.tags" :key="tag" class="card-tag">{{ tag }}</span></span>
            <span class="card-group"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2" /></svg>{{ groupNames.get(ticket.group_id) ?? `Group ${ticket.group_id}` }}</span>
            <span class="card-footer">
              <span class="card-assignee"><span :class="['avatar', { unassigned: !ticket.assignee }]" aria-hidden="true">{{ ticket.assignee ? ticket.assignee.slice(0, 2).toUpperCase() : '–' }}</span>{{ ticket.assignee || "Unassigned" }}</span>
              <time :datetime="ticket.updated_at" :title="formatTicketTime(ticket.updated_at)">{{ new Date(ticket.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }}</time>
            </span>
          </button>
          <p v-if="!column.tickets.length" class="column-empty">No tickets here.</p>
        </div>
      </section>
    </div>
    <footer class="board-footer"><span>Click a ticket to view details and reply.</span><span>Drag a card to change status · Priority reflects its issue group</span></footer>
  </div>
</template>

<style scoped>
.ticket-board { display: flex; flex-direction: column; gap: 14px; flex: 1; min-height: 0; }
.kanban-board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; flex: 1; min-height: 0; }
.kanban-column { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.kanban-column.drop-target { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.column-head { display: flex; align-items: center; gap: 8px; padding: 15px 14px 7px; }
.column-head h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 0.9em; font-weight: 600; }
svg { flex-shrink: 0; }
.column-head svg { width: 16px; height: 16px; color: var(--muted); }
.in_progress .column-head svg { color: var(--status-running); }
.resolved .column-head svg { color: var(--success); }
.column-count { min-width: 22px; padding: 0 5px; border: 1px solid var(--border); border-radius: var(--radius-full); color: var(--muted); background: var(--bg); text-align: center; font-size: 0.75em; }
.column-description { margin: 0; padding: 0 14px 13px; color: var(--muted); font-size: 0.75em; }
.column-cards { display: flex; flex-direction: column; gap: 10px; overflow-y: auto; flex: 1; min-height: 0; padding: 0 10px 10px; scrollbar-width: thin; }
button.ticket-card { display: flex; flex-direction: column; flex-shrink: 0; gap: 12px; width: 100%; min-width: 0; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); color: var(--text); background: var(--bg); text-align: left; font: inherit; cursor: pointer; transition: border-color 0.15s ease, transform 0.15s ease; }
button.ticket-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.ticket-id { font-family: var(--mono); color: var(--muted); font-size: 0.7em; overflow-wrap: anywhere; }
.ticket-priority { display: inline-flex; gap: 4px; align-items: center; font-size: 0.72em; white-space: nowrap; color: var(--muted); }
.ticket-priority svg { width: 13px; height: 13px; }
.ticket-priority.urgent { color: var(--status-failed); }
.ticket-priority.high { color: var(--warning); }
.card-title { font-size: 0.94em; line-height: 1.45; font-weight: 600; overflow-wrap: anywhere; }
.card-description { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; margin-top: -6px; font-size: 0.8em; line-height: 1.55; color: var(--muted); overflow-wrap: anywhere; }
.card-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.card-tag { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 1px 6px; background: var(--code-bg); color: var(--muted); font-size: 0.7em; overflow-wrap: anywhere; }
.card-group { display: flex; align-items: center; gap: 5px; font-size: 0.73em; color: var(--muted); overflow-wrap: anywhere; }
.card-group svg { width: 13px; height: 13px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; border-top: 1px solid var(--border); padding-top: 10px; color: var(--muted); font-size: 0.73em; }
.card-assignee { display: flex; align-items: center; gap: 6px; min-width: 0; overflow-wrap: anywhere; }
.avatar { display: inline-grid; place-items: center; flex-shrink: 0; width: 21px; height: 21px; border-radius: var(--radius-full); color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--bg)); font-size: 9px; font-weight: 600; }
.avatar.unassigned { border: 1px dashed var(--border); background: var(--surface); color: var(--muted); }
time { white-space: nowrap; }
.column-empty { padding: 14px 10px; color: var(--muted); text-align: center; font-size: 0.85em; }
.board-footer { display: flex; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 0.75em; }
.mobile-column-control { display: none; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (min-width: 768px) and (max-width: 1100px) {
  .kanban-board { grid-template-columns: repeat(4, minmax(245px, 1fr)); overflow-x: auto; gap: 12px; }
}
@media (max-width: 767px) {
  .mobile-column-control { display: block; }
  .mobile-column-control select { width: 100%; }
  .kanban-board { display: flex; flex-direction: column; }
  .kanban-column { flex: 1; }
  .kanban-column.mobile-hidden { display: none; }
  .card-description, .board-footer span:last-child { display: none; }
  .board-footer { font-size: 0.7em; }
}
@media (prefers-reduced-motion: reduce) {
  button.ticket-card { transition: none; }
  button.ticket-card:hover { transform: none; }
}
</style>
