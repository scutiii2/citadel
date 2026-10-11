<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  ticketsAdminClient,
  type AdminTicket,
  type TicketChanges,
  type TicketGroup,
  type TicketPriority,
  type TicketStatus,
} from "../../api/TicketsAdminClient";
import { errorMessage } from "../../utils/errors";
import {
  PRIORITY_LABELS,
  SOURCE_LABELS,
  STATUS_ICONS,
  STATUS_LABELS,
  formatTicketTime,
  type TicketFilterState,
} from "../../utils/ticketFormat";
import SegmentedControl from "../SegmentedControl.vue";
import ToggleSwitch from "../ToggleSwitch.vue";
import TicketDrawer from "./TicketDrawer.vue";
import TicketBoard from "./TicketBoard.vue";
import BaseModal from "../BaseModal.vue";
import "./admin.css";

/** Staff triage: a status board, groups of related reports, uncertain matches
 * for review, and the ticket drawer. Changes display server-confirmed state. */
const props = defineProps<{ filters: TicketFilterState }>();
const emit = defineEmits<{ filter: [value: TicketFilterState] }>();

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
] as const;
const MODE_OPTIONS = [
  { value: "board", label: "Board" },
  { value: "groups", label: "Groups" },
  { value: "review", label: "Needs review" },
] as const;
const PRIORITIES = Object.keys(PRIORITY_LABELS) as TicketPriority[];

const status = ref(props.filters.status);
const priority = ref(props.filters.priority);
const tag = ref(props.filters.tag);
const mode = ref(props.filters.mode);
const search = ref("");

const groups = ref<TicketGroup[]>([]);
const reviewTickets = ref<AdminTicket[]>([]);
const boardTickets = ref<AdminTicket[]>([]);
const expanded = ref<number | null>(null);
const groupTickets = ref<AdminTicket[]>([]);
const selected = ref<AdminTicket | null>(null);
const loadError = ref("");
const actionError = ref("");
const notice = ref("");
const replyReceipt = ref(0);
const busy = ref(false);
const loading = ref(true);

const tagOptions = computed(() => [...new Set([
  ...groups.value.flatMap((g) => g.tags),
  ...boardTickets.value.flatMap((t) => t.tags),
  ...reviewTickets.value.flatMap((t) => t.tags),
  ...(tag.value ? [tag.value] : []),
])].sort());
const groupNames = computed(() => new Map(groups.value.map(group => [group.id, group.title])));
const priorityOrder: Record<TicketPriority, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
const matches = (text: string) => text.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase());
const visibleGroups = computed(() => groups.value.filter(group => matches(`${group.id} ${group.title} ${group.tags.join(" ")}`)));
const visibleTickets = computed(() => (mode.value === "review" ? reviewTickets.value : boardTickets.value)
  .filter(ticket => matches(`${ticket.id} ${ticket.title} ${ticket.reporter} ${ticket.assignee ?? ""} ${ticket.tags.join(" ")} ${groupNames.value.get(ticket.group_id) ?? `Group ${ticket.group_id}`}`))
  .sort((a, b) => priorityOrder[a.effective_priority] - priorityOrder[b.effective_priority] || Date.parse(b.updated_at) - Date.parse(a.updated_at)));
const urgentCount = computed(() => mode.value === "groups"
  ? visibleGroups.value.filter(group => group.priority === "urgent").length
  : visibleTickets.value.filter(ticket => ticket.effective_priority === "urgent").length);
const issueGroupCount = computed(() => mode.value === "groups" ? visibleGroups.value.length : new Set(visibleTickets.value.map(ticket => ticket.group_id)).size);

// Only the newest list request may fill the page.
let loadSeq = 0;
async function load(): Promise<void> {
  const seq = ++loadSeq;
  loading.value = true;
  const filters = {
    ...(status.value !== "all" ? { status: status.value } : {}),
    ...(priority.value !== "all" ? { priority: priority.value } : {}),
    ...(tag.value ? { tag: tag.value } : {}),
  };
  try {
    if (mode.value === "board") {
      const [rows, names] = await Promise.all([
        ticketsAdminClient.listTickets({ ...filters, limit: 500 }),
        ticketsAdminClient.listGroups(),
      ]);
      if (seq !== loadSeq) return;
      boardTickets.value = rows;
      groups.value = names;
    } else if (mode.value === "review") {
      const rows = await ticketsAdminClient.listTickets({ ...filters, possible: true });
      if (seq !== loadSeq) return;
      reviewTickets.value = rows;
    } else {
      const rows = await ticketsAdminClient.listGroups(filters);
      if (seq !== loadSeq) return;
      groups.value = rows;
      if (expanded.value !== null && !rows.some((g) => g.id === expanded.value)) expanded.value = null;
    }
    loadError.value = "";
  } catch (err) {
    if (seq === loadSeq) loadError.value = errorMessage(err);
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}

// An expansion response belongs only to the group and request that started it.
let expandedSeq = 0;
async function loadExpanded(): Promise<void> {
  const seq = ++expandedSeq;
  const groupId = expanded.value;
  if (groupId === null) {
    groupTickets.value = [];
    return;
  }
  try {
    const rows = await ticketsAdminClient.listTickets({ group_id: groupId });
    if (seq === expandedSeq && expanded.value === groupId) groupTickets.value = rows;
  } catch (err) {
    if (seq === expandedSeq && expanded.value === groupId) loadError.value = errorMessage(err);
  }
}

watch([status, priority, tag, mode], () => {
  if (mode.value !== "groups") {
    expanded.value = null;
    groupTickets.value = [];
    ++expandedSeq;
  }
  emit("filter", { status: status.value, priority: priority.value, tag: tag.value, mode: mode.value });
  void load();
});
watch(
  () => props.filters,
  (next) => {
    status.value = next.status;
    priority.value = next.priority;
    tag.value = next.tag;
    mode.value = next.mode;
  },
);
onMounted(load);

async function toggle(group: TicketGroup): Promise<void> {
  expanded.value = expanded.value === group.id ? null : group.id;
  groupTickets.value = [];
  await loadExpanded();
}

// Closing or selecting another ticket invalidates pending detail responses.
let selectionSeq = 0;
async function refreshSelected(): Promise<void> {
  const seq = ++selectionSeq;
  const id = selected.value?.id;
  if (id === undefined) return;
  try {
    const ticket = await ticketsAdminClient.get(id);
    if (seq === selectionSeq) selected.value = ticket;
  } catch (err) {
    if (seq === selectionSeq) actionError.value = errorMessage(err);
  }
}

async function select(ticket: AdminTicket): Promise<void> {
  actionError.value = "";
  notice.value = "";
  selected.value = ticket;
  await refreshSelected();
}

function dismiss(): void {
  ++selectionSeq;
  selected.value = null;
}

/** Everything a change can touch: the lists and the open ticket. */
async function refreshAll(refreshDetail = true): Promise<void> {
  await Promise.all([load(), loadExpanded()]);
  if (refreshDetail) await refreshSelected();
}

async function act(call: () => Promise<unknown>, done = "Saved.", refreshDetail = true): Promise<void> {
  if (busy.value) return;
  actionError.value = "";
  notice.value = "";
  busy.value = true;
  try {
    await call();
    await refreshAll(refreshDetail);
    notice.value = done;
  } catch (err) {
    actionError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

function ticketAction(call: (id: number) => Promise<AdminTicket>, done = "Saved.", sentReply = false): Promise<void> {
  if (busy.value || !selected.value) return Promise.resolve();
  const id = selected.value.id;
  const seq = ++selectionSeq; // Supersede any earlier detail GET.
  return act(async () => {
    const confirmed = await call(id);
    if (seq === selectionSeq && selected.value?.id === id) {
      selected.value = confirmed;
      if (sentReply) ++replyReceipt.value;
    }
  }, done, false);
}
const update = (changes: TicketChanges) => ticketAction(id => ticketsAdminClient.update(id, changes));
const comment = (body: string) => ticketAction(id => ticketsAdminClient.comment(id, body), "Reply sent.", true);
const move = (groupId: number | null) =>
  ticketAction(id => ticketsAdminClient.move(id, groupId), groupId === null ? "Split out into a new group." : `Moved to group ${groupId}.`);

function changeBoardStatus(ticket: AdminTicket, next: TicketStatus): void {
  if (busy.value || loading.value || ticket.status === next) return;
  // Apply only the PATCH response; a rejected change leaves the card in place.
  const seq = selected.value?.id === ticket.id ? ++selectionSeq : null;
  void act(async () => {
    const confirmed = await ticketsAdminClient.update(ticket.id, { status: next });
    boardTickets.value = boardTickets.value.map(row => row.id === confirmed.id ? confirmed : row);
    if (seq !== null && seq === selectionSeq && selected.value?.id === confirmed.id) selected.value = confirmed;
  }, `Ticket #${ticket.id} moved to ${STATUS_LABELS[next]}.`, false);
}

/** The shown value stays the server's until the reload brings the new one. */
function setGroupPriority(group: TicketGroup, event: Event): void {
  const element = event.target as HTMLSelectElement;
  const value = element.value as TicketPriority;
  element.value = group.priority;
  if (value !== group.priority) void act(() => ticketsAdminClient.updateGroup(group.id, { priority: value }));
}

function setPinned(group: TicketGroup, event: Event): void {
  const element = event.target as HTMLInputElement;
  const value = element.checked;
  element.checked = group.priority_pinned;
  void act(() => ticketsAdminClient.updateGroup(group.id, { pinned: value }));
}
</script>

<template>
  <div class="admin-panel tickets-panel" :aria-busy="loading || busy">
    <div class="toolbar">
      <SegmentedControl v-model="mode" :options="MODE_OPTIONS" aria-label="Ticket view" />
      <div class="ticket-filters">
        <label class="ticket-search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0" /></svg>
          <input v-model="search" type="search" aria-label="Search tickets" placeholder="Search tickets…" />
        </label>
        <template v-if="mode === 'groups'">
          <SegmentedControl v-model="status" :options="STATUS_OPTIONS" label="Status" aria-label="Ticket status" />
        </template>
        <label class="field">
          <select v-model="priority" aria-label="Priority filter">
            <option value="all">All priorities</option>
            <option v-for="p in PRIORITIES" :key="p" :value="p">{{ PRIORITY_LABELS[p] }}</option>
          </select>
        </label>
        <label class="field">
          <select v-model="tag" aria-label="Tag filter">
            <option value="">All tags</option>
            <option v-for="t in tagOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <button type="button" class="small refresh" :disabled="loading || busy" :aria-busy="loading" @click="load">
          <svg :class="{ spinning: loading }" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 3M18 18a8 8 0 0 1-13-3" /></svg>Refresh
        </button>
      </div>
    </div>

    <div class="ticket-summary">
      <span v-if="mode === 'groups'"><strong>{{ visibleGroups.length }}</strong> groups</span>
      <span v-else><strong>{{ visibleTickets.length }}</strong> tickets</span>
      <span class="summary-urgent"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 21h20zM12 9v5M12 17h.01" /></svg>{{ urgentCount }} urgent</span>
      <span v-if="mode !== 'groups'" class="summary-groups"><strong>{{ issueGroupCount }}</strong> issue groups</span>
      <span class="summary-sort">{{ mode === 'groups' ? 'Similar reports grouped together' : 'Sorted by priority' }}</span>
    </div>
    <p v-if="mode !== 'groups' && status !== 'all'" class="active-status">
      Showing {{ STATUS_LABELS[status] }} tickets.
      <button type="button" class="small" @click="status = 'all'">Show all statuses</button>
    </p>
    <p v-if="mode === 'board' && boardTickets.length >= 500" class="muted limit-note">Showing the latest 500 matching tickets. Filter by priority or tag to narrow the board.</p>

    <p v-if="loadError" class="error" role="alert">Could not load tickets: {{ loadError }}</p>
    <p v-if="actionError && !selected" class="error" role="alert">{{ actionError }}</p>
    <p v-if="notice && !selected" class="notice" role="status">{{ notice }}</p>

    <p v-if="loading" class="muted loading" role="status">Loading tickets…</p>
    <TicketBoard v-if="mode === 'board'" :tickets="visibleTickets" :groups="groups" :busy="busy || loading" :status-filter="status" @select="select" @status="changeBoardStatus" />

    <div v-else class="layout">
      <div class="list">
        <template v-if="mode === 'groups'">
          <p v-if="visibleGroups.length === 0 && !loadError && !loading" class="muted empty">No tickets match.</p>
          <div v-for="g in visibleGroups" :key="g.id" class="group">
            <div class="group-row card">
              <button type="button" class="expand" :aria-expanded="expanded === g.id" @click="toggle(g)">
                <span class="title">{{ g.title }}</span>
                <span class="muted summary">
                  Group {{ g.id }} · {{ g.ticket_count }} {{ g.ticket_count === 1 ? "ticket" : "tickets" }} · {{ g.recent_count }} in 24 h ·
                  {{ g.open_count }} open
                </span>
              </button>
              <div class="chips">
                <span v-for="t in g.tags" :key="t" class="chip">{{ t }}</span>
              </div>
              <div class="priority">
                <label>
                  Priority
                  <select :aria-label="`Priority of group ${g.id}`" :value="g.priority" :disabled="busy" @change="setGroupPriority(g, $event)">
                    <option v-for="p in PRIORITIES" :key="p" :value="p">{{ PRIORITY_LABELS[p] }}</option>
                  </select>
                </label>
                <ToggleSwitch
                  small
                  :checked="g.priority_pinned"
                  :disabled="busy"
                  :aria-label="`Pin priority of group ${g.id}`"
                  title="Pinned: set by hand, never raised automatically"
                  @change="setPinned(g, $event)"
                >
                  Pinned
                </ToggleSwitch>
              </div>
            </div>
            <ul v-if="expanded === g.id" class="group-tickets">
              <li v-for="t in groupTickets" :key="t.id">
                <button type="button" class="ticket-link" :aria-pressed="selected?.id === t.id" @click="select(t)">
                  <span class="title">#{{ t.id }} {{ t.title }}</span>
                  <span class="meta">
                    <span>{{ t.reporter }}</span>
                    <span class="badge">{{ SOURCE_LABELS[t.source] }}</span>
                    <span class="status">
                      <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[t.status]" /></svg>{{ STATUS_LABELS[t.status] }}
                    </span>
                    <span class="muted">{{ formatTicketTime(t.updated_at) }}</span>
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </template>

        <template v-else>
          <p v-if="visibleTickets.length === 0 && !loadError && !loading" class="muted empty">{{ search || priority !== 'all' || tag || status !== 'all' ? 'No tickets match.' : 'Nothing needs review.' }}</p>
          <ul class="group-tickets review">
            <li v-for="t in visibleTickets" :key="t.id">
              <button type="button" class="ticket-link" :aria-pressed="selected?.id === t.id" @click="select(t)">
                <span class="title">#{{ t.id }} {{ t.title }}</span>
                <span class="meta">
                  <span>{{ t.reporter }}</span>
                  <span class="badge">May belong to group {{ t.possible_group_id }}</span>
                  <span class="muted">Now in group {{ t.group_id }}</span>
                </span>
              </button>
            </li>
          </ul>
        </template>
      </div>

    </div>

    <BaseModal :open="selected !== null" :title="`Ticket #${selected?.id ?? ''}`" side class="ticket-dialog" @close="dismiss">
      <TicketDrawer
        v-if="selected"
        :ticket="selected"
        :busy="busy"
        :error="actionError"
        :notice="notice"
        :reply-receipt="replyReceipt"
        @close="dismiss"
        @update="update"
        @comment="comment"
        @move="move"
      />
    </BaseModal>
  </div>
</template>

<style scoped>
.tickets-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 16px;
  margin-bottom: 16px;
}
.ticket-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; }
.ticket-search { display: flex; align-items: center; gap: 7px; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 7px 10px; color: var(--muted); }
.ticket-search svg { width: 17px; height: 17px; }
.tickets-panel .ticket-search input[type="search"] { width: 150px; min-width: 0; padding: 0; border: none; border-radius: 0; color: var(--text); background: transparent; font: inherit; font-size: 0.85em; }
.ticket-search:focus-within { border-color: var(--accent); }
.ticket-filters .field select { border-radius: var(--radius-full); }
button.refresh { display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px; }
.refresh svg { width: 16px; height: 16px; }
.spinning { animation: ticket-refresh 0.8s linear infinite; }
@keyframes ticket-refresh { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinning { animation: none; } }
.ticket-summary { display: flex; align-items: center; gap: 16px; color: var(--muted); font-size: 0.8em; margin-bottom: 22px; }
.ticket-summary strong { color: var(--text); font-weight: 500; }
.summary-urgent { display: inline-flex; align-items: center; gap: 5px; color: var(--status-failed); }
.summary-urgent svg { width: 14px; height: 14px; }
.summary-sort { margin-left: auto; }
.loading, .limit-note { margin: 0 0 12px; font-size: 0.85em; }
.active-status { display: flex; align-items: center; gap: 12px; margin: 0 0 12px; color: var(--muted); font-size: 0.85em; }
.tickets-panel :deep(.ticket-dialog > header) { display: none; }
.tickets-panel :deep(.ticket-dialog .drawer) { padding: 0; border: none; background: transparent; }
.field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.8em;
  color: var(--muted);
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  min-height: 0;
  overflow-y: auto;
}
.group {
  margin-bottom: 10px;
}
.group-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 14px;
  margin-bottom: 0;
}
.expand {
  display: flex;
  flex: 1 1 220px;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 0;
  border: none;
  color: var(--text);
  background: none;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.title {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.summary {
  font-size: 0.85em;
}
.priority {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.85em;
}
.priority label {
  display: flex;
  align-items: center;
  gap: 6px;
}
.group-tickets {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 6px 0 0 14px;
  padding: 0;
  list-style: none;
}
.ticket-link {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.ticket-link:hover,
.ticket-link[aria-pressed="true"] {
  border-color: var(--accent);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 10px;
  font-size: 0.85em;
}
.status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.status svg {
  width: 14px;
  height: 14px;
}
.empty {
  margin: 16px 0;
}
@media (max-width: 767px) {
  .toolbar { gap: 14px; }
  .ticket-filters { width: 100%; }
  .ticket-search { width: 100%; }
  .ticket-search input { flex: 1; }
  .field { flex: 1; }
  .ticket-summary { gap: 12px; margin-bottom: 16px; font-size: 0.75em; }
  .summary-groups { display: none; }
  button.refresh { font-size: 0.75em; }
  .group-tickets {
    margin-left: 0;
  }
}
</style>
