<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
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
const search = ref("");
const sort = ref("newest");
const filterOptions = computed(() => FILTER_OPTIONS.map(option => ({
  ...option,
  label: `${option.label} (${option.value === "all" ? tickets.value.length : tickets.value.filter(ticket => ticket.status === option.value).length})`,
})));
const visibleTickets = computed(() => tickets.value
  .filter(ticket => (filter.value === "all" || ticket.status === filter.value)
    && ticket.title.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()))
  .sort((a, b) => (Date.parse(b.updated_at) - Date.parse(a.updated_at)) * (sort.value === "newest" ? 1 : -1)));
const loading = ref(true);
const loadError = ref("");
const notice = ref("");
const route = useRoute();
const router = useRouter();

// Only the newest list request may fill the page.
let loadSeq = 0;
let listPending = false;
let seenVersion = 0;
const seenResults = new Map<number, { version: number; hasUnread: boolean }>();
async function load(): Promise<void> {
  const seq = ++loadSeq;
  listPending = true;
  const version = seenVersion;
  try {
    const rows = await ticketsClient.list(undefined);
    if (seq !== loadSeq) return;
    tickets.value = rows.map(row => {
      const seen = seenResults.get(row.id);
      return seen && seen.version > version ? { ...row, has_unread: seen.hasUnread } : row;
    });
    loadError.value = "";
  } catch (err) {
    if (seq === loadSeq) loadError.value = errorMessage(err);
  } finally {
    if (seq === loadSeq) {
      loading.value = false;
      listPending = false;
    }
  }
}
let pollTimer: ReturnType<typeof setInterval> | undefined;
function stopPolling(): void {
  clearInterval(pollTimer);
  pollTimer = undefined;
}
function updatePolling(): void {
  stopPolling();
  if (document.hidden) return;
  if (!listPending) void load();
  pollTimer = setInterval(() => { if (!listPending) void load(); }, 30_000);
}
onMounted(() => {
  document.addEventListener("visibilitychange", updatePolling);
  if (document.hidden) void load();
  else updatePolling();
});

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
const detailOpen = ref(false);
const detailLoading = ref(false);
const detailError = ref("");
const reply = ref("");
const replying = ref(false);
const confirmOpen = ref(false);
const closing = ref(false);
const timelineStage = computed(() => current.value?.status === "open" ? 0 : current.value?.status === "in_progress" ? 1 : 2);
const timeline = computed(() => [
  { label: "Open", at: current.value?.created_at },
  { label: "In progress", at: null },
  { label: "Resolved", at: current.value?.closed_at },
]);

// Dismissal and a newer selection invalidate pending detail responses.
let detailSeq = 0;
let activeDetailId: number | null = null;
function open(ticket: Ticket): void {
  current.value = ticket;
  void loadDetail(ticket.id);
  void router.push(`/tickets/${ticket.id}`);
}

async function loadDetail(id: number): Promise<void> {
  const seq = ++detailSeq;
  activeDetailId = id;
  current.value = current.value?.id === id ? current.value : tickets.value.find(ticket => ticket.id === id) ?? null;
  detailOpen.value = true;
  detailLoading.value = true;
  detailError.value = "";
  reply.value = "";
  try {
    const loaded = await ticketsClient.get(id);
    if (seq === detailSeq) {
      current.value = loaded;
      seenResults.set(id, { version: ++seenVersion, hasUnread: loaded.has_unread ?? false });
      tickets.value = tickets.value.map(row => row.id === id ? { ...row, has_unread: loaded.has_unread ?? false } : row);
      window.dispatchEvent(new Event("tickets-seen"));
    }
  } catch (err) {
    if (seq === detailSeq) detailError.value = errorMessage(err);
  } finally {
    if (seq === detailSeq) detailLoading.value = false;
  }
}

function dismiss(): void {
  ++detailSeq;
  activeDetailId = null;
  current.value = null;
  detailOpen.value = false;
  detailLoading.value = false;
  confirmOpen.value = false;
  void router.replace("/tickets");
}

watch(() => route.params.id, value => {
  if (!value) {
    dismiss();
    return;
  }
  const id = Number(value);
  if (!/^\d+$/.test(String(value)) || !Number.isSafeInteger(id) || id < 1) {
    ++detailSeq;
    activeDetailId = null;
    current.value = null;
    detailOpen.value = true;
    detailLoading.value = false;
    detailError.value = "Invalid ticket id.";
    return;
  }
  if (!detailOpen.value || activeDetailId !== id) void loadDetail(id);
}, { immediate: true });

onUnmounted(() => {
  ++detailSeq;
  ++loadSeq;
  stopPolling();
  document.removeEventListener("visibilitychange", updatePolling);
});

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

async function reopenTicket(): Promise<void> {
  if (!current.value || closing.value || replying.value) return;
  const seq = ++detailSeq;
  closing.value = true;
  detailError.value = "";
  try {
    const updated = await ticketsClient.reopen(current.value.id);
    if (seq === detailSeq) current.value = updated;
    await load();
  } catch (err) {
    if (seq === detailSeq) detailError.value = errorMessage(err);
  } finally {
    closing.value = false;
  }
}
</script>

<template>
  <PageLayout title="Tickets" description="Report a bug, suggest a feature, or ask for help. Support answers here." class="tickets info-content">
    <template #actions>
      <button type="button" class="primary" @click="startNew">New ticket</button>
    </template>
    <div class="column">
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <SegmentedControl v-model="filter" :options="filterOptions" label="Status" aria-label="Ticket status" />
      <div class="list-controls">
        <label class="search-control">Search titles<input v-model="search" type="search" aria-label="Search ticket titles" placeholder="Search your tickets" /></label>
        <label>Sort<select v-model="sort" aria-label="Sort tickets"><option value="newest">Recently updated</option><option value="oldest">Oldest update first</option></select></label>
      </div>

      <p v-if="loadError" class="error" role="alert">Could not load your tickets: {{ loadError }}</p>
      <p v-if="loading" class="muted">Loading …</p>
      <p v-else-if="visibleTickets.length === 0 && !loadError" class="muted">
        {{ search.trim() ? "No tickets match your search." : filter === "all" ? "You have no tickets yet." : "No tickets with this status." }}
      </p>
      <ul v-else class="list">
        <li v-for="t in visibleTickets" :key="t.id">
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
        <label>Title<input v-model="draft.title" type="text" maxlength="120" aria-label="Title" aria-describedby="ticket-title-count" :disabled="saving" /><span id="ticket-title-count" class="character-count">{{ draft.title.length }}/120</span></label>
        <label>
          Description
          <textarea v-model="draft.description" rows="6" maxlength="4000" aria-label="Description" aria-describedby="ticket-description-count" :disabled="saving" />
          <span id="ticket-description-count" class="character-count">{{ draft.description.length }}/4000</span>
        </label>
        <p v-if="formError" class="form-error error" role="alert">{{ formError }}</p>
        <div class="actions">
          <button type="button" class="chip" @click="newOpen = false">Cancel</button>
          <button type="submit" class="primary submit-ticket" :disabled="!canSubmit" :aria-busy="saving">Submit</button>
        </div>
      </form>
    </BaseModal>

    <BaseModal :open="detailOpen" :title="current ? `Ticket #${current.id}` : route.params.id ? `Ticket #${route.params.id}` : 'Ticket'" @close="dismiss">
      <p v-if="detailLoading && !current" class="muted" role="status">Loading …</p>
      <p v-if="detailError" class="error" role="alert">{{ detailError }}</p>
      <template v-if="current">
        <h3 class="detail-title">{{ current.title }}</h3>
        <p class="meta">
          <span class="badge">{{ TYPE_LABELS[current.type] }}</span>
          <span class="status">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[current.status]" /></svg>{{ STATUS_LABELS[current.status] }}
          </span>
          <span class="muted">Filed {{ formatTicketTime(current.created_at) }}</span>
        </p>
        <ol class="timeline" aria-label="Ticket status timeline">
          <li v-for="(step, index) in timeline" :key="step.label" :class="{ reached: index <= timelineStage }" :aria-current="index === timelineStage ? 'step' : undefined">
            <span>{{ step.label }}</span>
            <time v-if="step.at" :datetime="step.at">{{ formatTicketTime(step.at) }}</time>
          </li>
        </ol>
        <p class="text">{{ current.description }}</p>

        <ul v-if="current.comments?.length" class="thread" aria-label="Comments">
          <li v-for="c in current.comments" :key="c.id" :class="{ own: c.author_role === 'reporter' || c.author_role === 'ai', system: c.author_role === 'system' }">
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
            <button v-if="current.status === 'closed' || current.status === 'resolved'" type="button" class="chip" :disabled="closing || replying" :aria-busy="closing" @click="reopenTicket">Reopen ticket</button>
            <button v-else type="button" class="chip" :disabled="closing || replying" @click="confirmOpen = true">Close ticket</button>
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
  </PageLayout>
</template>

<style scoped>
.list-controls { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-top: 12px; }
.list-controls label { display: flex; flex-direction: column; gap: 4px; font-size: 0.85em; }
.search-control { flex: 1; min-width: 160px; }
.list-controls input, .list-controls select { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.character-count { color: var(--muted); font-size: 0.85em; text-align: right; }
.timeline { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; padding: 0; margin: 16px 0; list-style: none; font-size: 0.85em; }
.timeline li { display: flex; flex-direction: column; gap: 4px; border-top: 2px solid var(--border); padding-top: 8px; color: var(--muted); }
.timeline li.reached { border-color: var(--accent); }
.timeline li[aria-current="step"] > span { color: var(--text); font-weight: 600; }
.timeline time { font-size: 0.9em; overflow-wrap: anywhere; }
.thread li { margin-right: 24px; }
.thread li.own { margin-left: 24px; margin-right: 0; }
.thread li.system { margin: 0; }
.reply .actions { justify-content: space-between; }
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
