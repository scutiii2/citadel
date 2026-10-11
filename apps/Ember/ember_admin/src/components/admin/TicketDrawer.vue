<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { AdminTicket, TicketChanges, TicketPriority, TicketStatus } from "../../api/TicketsAdminClient";
import {
  COMMENT_ROLE_LABELS,
  PRIORITY_LABELS,
  SOURCE_LABELS,
  STATUS_ICONS,
  STATUS_LABELS,
  TYPE_LABELS,
  formatTicketTime,
} from "../../utils/ticketFormat";
import "./admin.css";

/** One ticket for staff: details, the reporter's context (unverified), status,
 * priority, assignee, tags, group, and the thread. It only shows state and
 * reports what staff chose (the parent runs the call and passes the fresh
 * ticket back); `busy` disables the controls while a call is in flight. */
const props = defineProps<{ ticket: AdminTicket; busy: boolean; error: string; notice: string; replyReceipt?: number }>();
const emit = defineEmits<{
  close: [];
  update: [changes: TicketChanges];
  comment: [body: string];
  move: [groupId: number | null];
}>();

const STATUSES = Object.keys(STATUS_LABELS) as TicketStatus[];
const PRIORITIES = Object.keys(PRIORITY_LABELS) as TicketPriority[];

const assignee = ref("");
const tags = ref("");
const groupNumber = ref("");
const reply = ref("");

watch(
  () => props.ticket,
  (ticket, previous) => {
    const changed = previous?.id !== ticket.id;
    // Refresh clean fields; preserve unsaved edits to this same ticket.
    if (changed || assignee.value === (previous?.assignee ?? "")) assignee.value = ticket.assignee ?? "";
    if (changed || tags.value === previous?.tags.join(", ")) tags.value = ticket.tags.join(", ");
    if (changed) {
      groupNumber.value = "";
      reply.value = "";
    }
  },
  { immediate: true },
);

watch(() => props.replyReceipt, () => { reply.value = ""; });

const reported = computed(() => Object.entries(props.ticket.context.reported ?? {}));
const verified = computed(() => Object.entries(props.ticket.context.verified ?? {}));
const groupId = computed(() => {
  const text = groupNumber.value.trim();
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
});

/** A server-confirmed control: report the choice, then show the server's value again until the ticket comes back. */
function choose<K extends "status" | "priority">(key: K, event: Event, current: string): void {
  const select = event.target as HTMLSelectElement;
  const value = select.value;
  select.value = current;
  if (value !== current) emit("update", { [key]: value } as TicketChanges);
}

function saveTags(): void {
  emit("update", { tags: tags.value.split(",").map((t) => t.trim()).filter(Boolean) });
}

function send(): void {
  if (reply.value.trim() !== "") emit("comment", reply.value.trim());
}
</script>

<template>
  <aside class="drawer admin-panel" :aria-label="`Ticket ${ticket.id}`">
    <header class="head">
      <div>
        <b class="name">#{{ ticket.id }} {{ ticket.title }}</b>
        <p class="meta muted">
          {{ TYPE_LABELS[ticket.type] }} · from <b>{{ ticket.reporter }}</b> · {{ SOURCE_LABELS[ticket.source] }}
        </p>
        <p class="meta">
          <span class="status">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[ticket.status]" /></svg>{{ STATUS_LABELS[ticket.status] }}
          </span>
          <span>Priority: {{ PRIORITY_LABELS[ticket.effective_priority] }}</span>
          <span class="muted">Group {{ ticket.group_id }}</span>
        </p>
        <p class="meta muted">Filed {{ formatTicketTime(ticket.created_at) }} · updated {{ formatTicketTime(ticket.updated_at) }}</p>
      </div>
      <button type="button" class="x" aria-label="Close" @click="emit('close')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>

    <p class="text">{{ ticket.description }}</p>

    <section v-if="reported.length || verified.length" class="context">
      <h4>Context</h4>
      <template v-if="reported.length">
        <p class="muted small-text">Reported by the reporter or a model (unverified)</p>
        <dl>
          <template v-for="[key, value] in reported" :key="`r-${key}`">
            <dt>{{ key }}</dt>
            <dd class="mono">{{ value }}</dd>
          </template>
        </dl>
      </template>
      <template v-if="verified.length">
        <p class="muted small-text">Added by ember_api</p>
        <dl>
          <template v-for="[key, value] in verified" :key="`v-${key}`">
            <dt>{{ key }}</dt>
            <dd class="mono">{{ value }}</dd>
          </template>
        </dl>
      </template>
    </section>

    <section class="controls">
      <label>
        Status
        <select aria-label="Status" :disabled="busy" :value="ticket.status" @change="choose('status', $event, ticket.status)">
          <option v-for="s in STATUSES" :key="s" :value="s">{{ STATUS_LABELS[s] }}</option>
        </select>
      </label>
      <label>
        Priority
        <select aria-label="Priority" :disabled="busy" :value="ticket.priority" @change="choose('priority', $event, ticket.priority)">
          <option v-for="p in PRIORITIES" :key="p" :value="p">{{ PRIORITY_LABELS[p] }}</option>
        </select>
      </label>
      <div class="row-form">
        <input v-model="assignee" type="text" maxlength="64" aria-label="Assignee" placeholder="Assignee (username)" :disabled="busy" />
        <button type="button" class="small save-assignee" :disabled="busy" @click="emit('update', { assignee })">Save</button>
      </div>
      <div class="row-form">
        <input v-model="tags" type="text" aria-label="Tags" placeholder="Tags, separated by commas" :disabled="busy" />
        <button type="button" class="small save-tags" :disabled="busy" @click="saveTags">Save</button>
      </div>
      <div class="row-form">
        <input v-model="groupNumber" type="text" inputmode="numeric" aria-label="Group number" placeholder="Group number" :disabled="busy" />
        <button type="button" class="small move" :disabled="busy || groupId === null" @click="emit('move', groupId)">Move</button>
        <button type="button" class="small split" :disabled="busy" @click="emit('move', null)">Split out</button>
      </div>
      <button
        v-if="ticket.possible_group_id !== null"
        type="button"
        class="small move-hint"
        :disabled="busy"
        @click="emit('move', ticket.possible_group_id)"
      >
        May belong to group {{ ticket.possible_group_id }}: move there
      </button>
    </section>

    <section class="thread-section">
      <h4>Thread</h4>
      <p v-if="!ticket.comments?.length" class="muted">No comments yet.</p>
      <ul v-else class="thread" aria-label="Comments">
        <li v-for="c in ticket.comments" :key="c.id">
          <div class="who">
            <b>{{ c.author }}</b> <span class="muted">{{ COMMENT_ROLE_LABELS[c.author_role] }} · {{ formatTicketTime(c.created_at) }}</span>
          </div>
          <p class="text">{{ c.body }}</p>
        </li>
      </ul>
      <form class="reply" @submit.prevent="send">
        <textarea v-model="reply" rows="3" maxlength="2000" aria-label="Reply" placeholder="Reply to the reporter or ask for details" :disabled="busy" />
        <button type="submit" class="primary send-reply" :disabled="busy || reply.trim() === ''" :aria-busy="busy">Reply</button>
      </form>
    </section>
  </aside>
</template>

<style scoped>
.drawer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.name {
  overflow-wrap: anywhere;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
  margin: 4px 0 0;
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
.x {
  padding: 4px;
  border: none;
  cursor: pointer;
  color: var(--muted);
  background: none;
}
.x svg {
  width: 18px;
  height: 18px;
}
.text {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.context dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 2px 10px;
  margin: 4px 0 8px;
  font-size: 0.85em;
}
.context dt {
  color: var(--muted);
}
.context dd {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.mono {
  font-family: var(--mono);
}
.small-text {
  margin: 4px 0 0;
  font-size: 0.8em;
}
.controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.controls label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.9em;
}
.thread {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0 0 10px;
  padding: 0;
  list-style: none;
}
.thread li {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.thread .who {
  font-size: 0.85em;
}
.thread .text {
  margin-top: 4px;
}
.reply {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.reply textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
  font: inherit;
  resize: vertical;
}
</style>
