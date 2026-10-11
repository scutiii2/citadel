<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  ticketsAdminClient,
  type AdminTicket,
  type TicketChanges,
  type TicketGroup,
  type TicketPriority,
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
import "./admin.css";

/** Staff triage: groups of similar tickets (Laya groups them), each expandable
 * to its tickets, a review list of tickets Laya was unsure about, and the
 * ticket drawer. Every control shows only what the server has confirmed. */
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
  { value: "groups", label: "Groups" },
  { value: "review", label: "Needs review" },
] as const;
const PRIORITIES = Object.keys(PRIORITY_LABELS) as TicketPriority[];

const status = ref(props.filters.status);
const priority = ref(props.filters.priority);
const tag = ref(props.filters.tag);
const mode = ref(props.filters.mode);

const groups = ref<TicketGroup[]>([]);
const reviewTickets = ref<AdminTicket[]>([]);
const expanded = ref<number | null>(null);
const groupTickets = ref<AdminTicket[]>([]);
const selected = ref<AdminTicket | null>(null);
const loadError = ref("");
const actionError = ref("");
const notice = ref("");
const replyReceipt = ref(0);
const busy = ref(false);
const loading = ref(true);

const tagOptions = computed(() => [...new Set([...groups.value.flatMap((g) => g.tags), ...(tag.value ? [tag.value] : [])])].sort());

// Only the newest list request may fill the page.
let loadSeq = 0;
async function load(): Promise<void> {
  const seq = ++loadSeq;
  try {
    if (mode.value === "review") {
      const rows = await ticketsAdminClient.listTickets({ possible: true });
      if (seq !== loadSeq) return;
      reviewTickets.value = rows;
    } else {
      const rows = await ticketsAdminClient.listGroups({
        ...(status.value !== "all" ? { status: status.value } : {}),
        ...(priority.value !== "all" ? { priority: priority.value } : {}),
        ...(tag.value ? { tag: tag.value } : {}),
      });
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
  <div class="admin-panel tickets-panel">
    <div class="toolbar">
      <SegmentedControl v-model="mode" :options="MODE_OPTIONS" label="View" aria-label="Ticket view" />
      <template v-if="mode === 'groups'">
        <SegmentedControl v-model="status" :options="STATUS_OPTIONS" label="Status" aria-label="Ticket status" />
        <label class="field">
          Priority
          <select v-model="priority" aria-label="Priority filter">
            <option value="all">All</option>
            <option v-for="p in PRIORITIES" :key="p" :value="p">{{ PRIORITY_LABELS[p] }}</option>
          </select>
        </label>
        <label class="field">
          Tag
          <select v-model="tag" aria-label="Tag filter">
            <option value="">All</option>
            <option v-for="t in tagOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
      </template>
    </div>

    <p v-if="loadError" class="error" role="alert">Could not load tickets: {{ loadError }}</p>
    <p v-if="actionError && !selected" class="error" role="alert">{{ actionError }}</p>
    <p v-if="notice && !selected" class="notice" role="status">{{ notice }}</p>

    <div :class="['layout', { open: selected }]">
      <div class="list">
        <p v-if="loading" class="muted">Loading …</p>

        <template v-else-if="mode === 'groups'">
          <p v-if="groups.length === 0 && !loadError" class="muted empty">No tickets match.</p>
          <div v-for="g in groups" :key="g.id" class="group">
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
          <p v-if="reviewTickets.length === 0 && !loadError" class="muted empty">Nothing needs review.</p>
          <ul class="group-tickets review">
            <li v-for="t in reviewTickets" :key="t.id">
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
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px 16px;
  margin-bottom: 14px;
}
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
}
.layout.open {
  grid-template-columns: minmax(0, 1fr) minmax(300px, 420px);
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
  .layout.open {
    grid-template-columns: minmax(0, 1fr);
  }
  .group-tickets {
    margin-left: 0;
  }
}
</style>
