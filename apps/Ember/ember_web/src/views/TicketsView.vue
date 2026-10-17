<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ticketsClient, type NewTicket, type Ticket, type TicketStatus } from "../api/TicketsClient";
import BaseModal from "../components/BaseModal.vue";
import ConfirmModal from "../components/ConfirmModal.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import "../components/infoPage.css";
import { errorMessage } from "../utils/errors";
import { COMMENT_ROLE_LABELS, STATUS_ICONS, STATUS_LABELS, TYPE_LABELS, formatTicketTime } from "../utils/tickets";

/** The signed-in account's own tickets (ember_api's /api/tickets): report a
 * bug or suggest a feature, follow what support answers, add details, close. */

type Filter = "all" | TicketStatus;
const FILTER_OPTIONS = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
] as const;
const TYPE_OPTIONS = [
  { value: "bug", label: "Bug" },
  { value: "feature", label: "Feature" },
  { value: "other", label: "Other" },
] as const;

const filter = ref<Filter>("all");
const tickets = ref<Ticket[]>([]);
const loading = ref(true);
const loadError = ref("");
const notice = ref("");

// Only the newest list request may fill the page.
let loadSeq = 0;
async function load(): Promise<void> {
  const seq = ++loadSeq;
  try {
    const rows = await ticketsClient.list(filter.value === "all" ? undefined : filter.value);
    if (seq !== loadSeq) return;
    tickets.value = rows;
    loadError.value = "";
  } catch (err) {
    if (seq === loadSeq) loadError.value = errorMessage(err);
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}
watch(filter, load);
onMounted(load);

// ---- new ticket ----
const newOpen = ref(false);
const draft = reactive<NewTicket>({ type: "bug", title: "", description: "" });
const saving = ref(false);
const formError = ref("");
const canSubmit = computed(() => draft.title.trim() !== "" && draft.description.trim() !== "" && !saving.value);

function startNew(): void {
  formError.value = "";
  newOpen.value = true;
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return;
  saving.value = true;
  formError.value = "";
  try {
    const created = await ticketsClient.create({ type: draft.type, title: draft.title.trim(), description: draft.description.trim() });
    notice.value = created.group_size > 1
      ? `Ticket #${created.ticket.id} filed. ${created.group_size - 1} other ${created.group_size === 2 ? 'person' : 'people'} reported something similar, so yours is grouped with them.`
      : `Ticket ${created.ticket.id} filed. Support will review it.`;
    draft.type = "bug";
    draft.title = "";
    draft.description = "";
    newOpen.value = false;
    await load();
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

// ---- one ticket ----
const current = ref<Ticket | null>(null);
const detailError = ref("");
const reply = ref("");
const replying = ref(false);
const confirmOpen = ref(false);
const closing = ref(false);

// Dismissal and a newer selection invalidate pending detail responses.
let detailSeq = 0;
async function open(ticket: Ticket): Promise<void> {
  const seq = ++detailSeq;
  current.value = ticket;
  detailError.value = "";
  reply.value = "";
  try {
    const loaded = await ticketsClient.get(ticket.id);
    if (seq === detailSeq) {
      current.value = loaded;
      tickets.value = tickets.value.map(row => row.id === ticket.id ? { ...row, has_unread: loaded.has_unread ?? false } : row);
      window.dispatchEvent(new Event("tickets-seen"));
    }
  } catch (err) {
    if (seq === detailSeq) detailError.value = errorMessage(err);
  }
}

function dismiss(): void {
  ++detailSeq;
  current.value = null;
  confirmOpen.value = false;
}

async function sendReply(): Promise<void> {
  if (!current.value || reply.value.trim() === "" || replying.value || closing.value) return;
  const seq = ++detailSeq;
  replying.value = true;
  detailError.value = "";
  try {
    const updated = await ticketsClient.comment(current.value.id, reply.value.trim());
    if (seq === detailSeq) {
      current.value = updated;
      reply.value = "";
    }
  } catch (err) {
    if (seq === detailSeq) detailError.value = errorMessage(err);
  } finally {
    replying.value = false;
  }
}

async function closeTicket(): Promise<void> {
  if (!current.value || closing.value || replying.value) return;
  const seq = ++detailSeq;
  closing.value = true;
  detailError.value = "";
  try {
    const updated = await ticketsClient.close(current.value.id);
    if (seq === detailSeq) {
      current.value = updated;
      confirmOpen.value = false;
    }
    await load();
  } catch (err) {
    if (seq === detailSeq) {
      detailError.value = errorMessage(err);
      confirmOpen.value = false;
    }
  } finally {
    closing.value = false;
  }
}
</script>

<template>
  <section class="info-page tickets">
    <div class="column page-column">
      <div class="top">
        <div>
          <h2 class="page-title">Tickets</h2>
          <p class="muted intro page-description">Report a bug, suggest a feature, or ask for help. Support answers here.</p>
        </div>
        <button type="button" class="primary" @click="startNew">New ticket</button>
      </div>

      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <SegmentedControl v-model="filter" :options="FILTER_OPTIONS" label="Status" aria-label="Ticket status" />

      <p v-if="loadError" class="error" role="alert">Could not load your tickets: {{ loadError }}</p>
      <p v-if="loading" class="muted">Loading …</p>
      <p v-else-if="tickets.length === 0 && !loadError" class="muted">
        {{ filter === "all" ? "You have no tickets yet." : "No tickets with this status." }}
      </p>
      <ul v-else class="list">
        <li v-for="t in tickets" :key="t.id">
          <button type="button" class="ticket-row card" :class="{ unread: t.has_unread }" @click="open(t)">
            <span class="title"><span v-if="t.has_unread" class="unread-dot" aria-hidden="true" />{{ t.title }}</span>
            <span v-if="t.has_unread" class="unread-label">Support replied</span>
            <span class="meta">
              <span class="badge">{{ TYPE_LABELS[t.type] }}</span>
              <span class="status">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[t.status]" /></svg>{{ STATUS_LABELS[t.status] }}
              </span>
              <span class="muted">#{{ t.id }} · updated {{ formatTicketTime(t.updated_at) }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>

    <BaseModal :open="newOpen" title="New ticket" @close="newOpen = false">
      <form class="form" @submit.prevent="submit">
        <SegmentedControl v-model="draft.type" :options="TYPE_OPTIONS.map(option => ({ ...option, disabled: saving }))" label="Type" aria-label="Ticket type" />
        <label>Title<input v-model="draft.title" type="text" maxlength="120" aria-label="Title" :disabled="saving" /></label>
        <label>
          Description
          <textarea v-model="draft.description" rows="6" maxlength="4000" aria-label="Description" :disabled="saving" />
        </label>
        <p v-if="formError" class="form-error error" role="alert">{{ formError }}</p>
        <div class="actions">
          <button type="button" class="chip" @click="newOpen = false">Cancel</button>
          <button type="submit" class="primary submit-ticket" :disabled="!canSubmit" :aria-busy="saving">Submit</button>
        </div>
      </form>
    </BaseModal>

    <BaseModal :open="current !== null" :title="current ? `Ticket #${current.id}` : 'Ticket'" @close="dismiss">
      <template v-if="current">
        <h3 class="detail-title">{{ current.title }}</h3>
        <p class="meta">
          <span class="badge">{{ TYPE_LABELS[current.type] }}</span>
          <span class="status">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[current.status]" /></svg>{{ STATUS_LABELS[current.status] }}
          </span>
          <span class="muted">Filed {{ formatTicketTime(current.created_at) }}</span>
        </p>
        <p class="text">{{ current.description }}</p>
        <p v-if="detailError" class="error" role="alert">{{ detailError }}</p>

        <ul v-if="current.comments?.length" class="thread" aria-label="Comments">
          <li v-for="c in current.comments" :key="c.id">
            <div class="who">
              <b>{{ COMMENT_ROLE_LABELS[c.author_role] }}</b>
              <span class="muted">{{ formatTicketTime(c.created_at) }}</span>
            </div>
            <p class="text">{{ c.body }}</p>
          </li>
        </ul>

        <form class="form reply" @submit.prevent="sendReply">
          <textarea v-model="reply" rows="3" maxlength="2000" aria-label="Reply" placeholder="Add details or answer a question" :disabled="replying || closing" />
          <div class="actions">
            <button v-if="current.status !== 'closed'" type="button" class="chip" @click="confirmOpen = true">Close ticket</button>
            <button type="submit" class="primary" :disabled="reply.trim() === '' || replying || closing" :aria-busy="replying">Send</button>
          </div>
        </form>
      </template>
    </BaseModal>

    <ConfirmModal
      :open="confirmOpen"
      title="Close this ticket?"
      message="Support will see it as closed. You can still add a comment later."
      confirm-label="Close the ticket"
      :busy="closing"
      @confirm="closeTicket"
      @close="confirmOpen = false"
    />
  </section>
</template>

<style scoped>
.top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}
.ticket-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  margin: 0;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.ticket-row:hover {
  border-color: var(--accent);
}
.ticket-row.unread { border-color: var(--accent); }
.unread-label { color: var(--accent); font-size: 0.85em; }
.unread-dot { display: inline-block; width: 8px; height: 8px; margin-right: 8px; border-radius: var(--radius-full); background: var(--accent); }
.title {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  margin: 0;
  font-size: 0.85em;
}
.badge {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  font-size: 0.9em;
  color: var(--muted);
}
.status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.status svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.notice {
  margin: 8px 0;
  color: var(--muted);
}
.form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.9em;
}
.form textarea,
.form input {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
  font: inherit;
  resize: vertical;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.detail-title {
  margin: 0 0 6px;
  overflow-wrap: anywhere;
}
.text {
  margin: 8px 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.thread {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
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
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.85em;
}
.thread .text {
  margin: 4px 0 0;
}
.reply {
  margin-top: 12px;
}
</style>
