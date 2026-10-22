<script setup lang="ts">
import PageLayout from "../../components/layout/PageLayout.vue";
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { ticketsClient, type NewTicket, type Ticket, type TicketStatus } from "./api/TicketsClient";
import BaseModal from "../../components/ui/dialogs/BaseModal.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import SegmentedControl from "../../components/ui/forms/SegmentedControl.vue";
import "../../components/layout/infoPage.css";
import { errorMessage } from "../../utils/errors";
import { COMMENT_ROLE_LABELS, STATUS_ICONS, STATUS_LABELS, TYPE_LABELS, formatTicketTime } from "./utils/tickets";

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
const replies = reactive<Record<number, string>>({});
const reply = computed({
  get: () => activeDetailId.value === null ? "" : replies[activeDetailId.value] ?? "",
  set: (value: string) => { if (activeDetailId.value !== null) replies[activeDetailId.value] = value; },
});
const discardDrafts = ref(false);
let leaveAnswer: ((value: boolean) => void) | null = null;
const hasDrafts = computed(() => !!draft.title.trim() || !!draft.description.trim() || Object.values(replies).some(value => !!value.trim()));
function answerLeave(discard: boolean): void {
  discardDrafts.value = false;
  leaveAnswer?.(discard);
  leaveAnswer = null;
}
onBeforeRouteLeave(to => {
  if (to.path === '/tickets' || /^\/tickets\/\d+$/.test(to.path)) return true;
  if (saving.value || replying.value) return false;
  if (!hasDrafts.value) return true;
  discardDrafts.value = true;
  return new Promise<boolean>(resolve => { leaveAnswer = resolve; });
});
function beforeUnload(event: BeforeUnloadEvent): void {
  if (hasDrafts.value) { event.preventDefault(); event.returnValue = ""; }
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onUnmounted(() => window.removeEventListener("beforeunload", beforeUnload));
const replying = ref(false);
const confirmOpen = ref(false);
const closing = ref(false);
const timelineStage = computed(() => current.value?.status === "open" ? 0 : current.value?.status === "in_progress" ? 1 : 2);
const timeline = computed(() => [
  { label: "Filed", at: current.value?.created_at },
  { label: "In progress", at: null },
  { label: current.value?.status === "closed" ? "Closed" : "Resolved", at: current.value?.closed_at },
]);

// Dismissal and a newer selection invalidate pending detail responses.
let detailSeq = 0;
const activeDetailId = ref<number | null>(null);
function open(ticket: Ticket): void {
  if (replying.value || closing.value) return;
  if (detailOpen.value && activeDetailId.value === ticket.id) {
    if (ticket.has_unread && !detailLoading.value) void loadDetail(ticket.id, true);
    return;
  }
  current.value = ticket;
  void loadDetail(ticket.id);
  void router.push(`/tickets/${ticket.id}`);
}

async function loadDetail(id: number, _preserveReply = false): Promise<void> {
  const seq = ++detailSeq;
  activeDetailId.value = id;
  current.value = current.value?.id === id ? current.value : tickets.value.find(ticket => ticket.id === id) ?? null;
  detailOpen.value = true;
  detailLoading.value = true;
  detailError.value = "";
  // Each ticket keeps its own unsent reply.
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
  activeDetailId.value = null;
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
    activeDetailId.value = null;
    current.value = null;
    detailOpen.value = true;
    detailLoading.value = false;
    detailError.value = "Invalid ticket id.";
    return;
  }
  if (!detailOpen.value || activeDetailId.value !== id) void loadDetail(id);
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
  <PageLayout title="Tickets" description="Report an issue, share an idea, or follow a support reply." class="tickets info-content" :class="{ 'thread-open': detailOpen }" wide fill>
    <template #actions>
      <button v-if="detailOpen" type="button" class="chip mobile-back" @click="dismiss">‹ All tickets</button>
      <button type="button" class="primary new-ticket" @click="startNew">New ticket</button>
    </template>
    <template #toolbar>
      <div class="list-controls">
        <label class="search-control"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg><input v-model="search" type="search" aria-label="Search ticket titles" placeholder="Search your ticket titles…" /></label>
        <label class="sort-control"><span class="sr-only">Sort</span><select v-model="sort" aria-label="Sort tickets"><option value="newest">Recently updated</option><option value="oldest">Oldest update first</option></select></label>
      </div>
      <SegmentedControl class="status-filters" v-model="filter" :options="filterOptions" aria-label="Ticket status" />
    </template>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="ticket-workspace" :class="{ reading: detailOpen }">
      <aside class="ticket-browser" aria-label="Your tickets">
        <div class="list-heading"><span>Your tickets</span><span>{{ visibleTickets.length }} tickets</span></div>
        <div v-if="loadError" class="load-error error" role="alert"><p>Could not load your tickets: {{ loadError }}</p><button type="button" class="chip" @click="load">Try again</button></div>
        <p v-if="loading" class="muted empty-message" role="status">Loading …</p>
        <p v-else-if="visibleTickets.length === 0 && !loadError" class="muted empty-message">{{ search.trim() ? "No tickets match your search." : filter === "all" ? "You have no tickets yet." : "No tickets with this status." }}</p>
        <ul v-else class="list" aria-label="Your ticket list">
          <li v-for="t in visibleTickets" :key="t.id">
            <button type="button" class="ticket-row" :class="{ unread: t.has_unread, active: current?.id === t.id && detailOpen }" :aria-current="current?.id === t.id && detailOpen ? 'true' : undefined" :disabled="replying || closing" @click="open(t)">
              <span class="row-top"><span>#{{ t.id }}</span><span class="badge">{{ TYPE_LABELS[t.type] }}</span></span>
              <span class="title">{{ t.title }}</span>
              <span v-if="t.has_unread" class="unread-label"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5" /></svg>Support replied</span>
              <span class="status"><svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[t.status]" /></svg>{{ STATUS_LABELS[t.status] }}</span>
              <span class="row-time muted">Updated {{ formatTicketTime(t.updated_at) }}</span>
            </button>
          </li>
        </ul>
        <p class="list-footer muted">Your reports and support conversations.<br>Only your own tickets appear here.</p>
      </aside>

      <section v-if="detailOpen" class="ticket-thread" role="region" :aria-label="current ? `Ticket #${current.id}` : route.params.id ? `Ticket #${route.params.id}` : 'Ticket'">
        <header class="detail-head">
          <span>{{ current ? `#${current.id}` : route.params.id ? `#${route.params.id}` : 'Ticket' }}<span v-if="current"> · {{ TYPE_LABELS[current.type] }}</span></span>
          <span v-if="current" class="status"><svg viewBox="0 0 24 24" aria-hidden="true"><path :d="STATUS_ICONS[current.status]" /></svg>{{ STATUS_LABELS[current.status] }}</span>
          <button type="button" class="close" aria-label="Close" title="Back to all tickets" @click="dismiss">×</button>
        </header>
        <p v-if="detailError" class="detail-error error" role="alert">{{ detailError }}</p>
        <div class="conversation" tabindex="0" aria-label="Ticket conversation">
          <p v-if="detailLoading" class="muted" role="status">Loading …</p>
          <template v-if="current">
            <h3 class="detail-title">{{ current.title }}</h3>
            <p class="filed muted">Filed {{ formatTicketTime(current.created_at) }}</p>
            <ol class="timeline" aria-label="Ticket status timeline">
              <li v-for="(step, index) in timeline" :key="step.label" :class="{ reached: index <= timelineStage }" :aria-current="index === timelineStage ? 'step' : undefined">
                <span>{{ step.label }}</span><time v-if="step.at" :datetime="step.at">{{ formatTicketTime(step.at) }}</time>
              </li>
            </ol>
            <section class="original-report"><div class="who"><b>You</b></div><p class="text">{{ current.description }}</p></section>
            <p v-if="current.comments?.length" class="conversation-label muted">Conversation</p>
            <ul v-if="current.comments?.length" class="thread" aria-label="Comments">
              <li v-for="c in current.comments" :key="c.id" :class="{ own: c.author_role === 'reporter' || c.author_role === 'ai', support: c.author_role === 'staff', system: c.author_role === 'system' }">
                <div class="who"><b>{{ COMMENT_ROLE_LABELS[c.author_role] }}</b><span class="muted">{{ formatTicketTime(c.created_at) }}</span></div>
                <p class="text">{{ c.body }}</p>
              </li>
            </ul>
          </template>
        </div>
        <form v-if="current" class="form reply" @submit.prevent="sendReply">
          <textarea v-model="reply" rows="2" maxlength="2000" aria-label="Reply" placeholder="Add details or reply to support…" :disabled="replying || closing" />
          <div class="actions">
            <button v-if="current.status === 'closed' || current.status === 'resolved'" type="button" class="chip manage-ticket" :disabled="closing || replying" :aria-busy="closing" @click="reopenTicket">Reopen ticket</button>
            <button v-else type="button" class="chip manage-ticket" :disabled="closing || replying" @click="confirmOpen = true">Close ticket</button>
            <button type="submit" class="primary send-reply" :disabled="reply.trim() === '' || replying || closing" :aria-busy="replying">Send</button>
          </div>
        </form>
      </section>
      <div v-else class="thread-placeholder"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4zM15 5v3m0 3v2m0 3v3" /></svg><h3>Your support conversation</h3><p>Choose a ticket to read replies, or start a new report.</p></div>
    </div>

    <BaseModal class="new-ticket-modal" :open="newOpen" title="New ticket" @close="newOpen = false">
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


    <ConfirmModal :open="confirmOpen" title="Close this ticket?" message="Support will see it as closed. You can still add a comment later." confirm-label="Close the ticket" :busy="closing" @confirm="closeTicket" @close="confirmOpen = false" />
    <ConfirmModal :open="discardDrafts" title="Discard ticket drafts?" message="Your unsent ticket and replies will be lost." confirm-label="Discard drafts" @confirm="answerLeave(true)" @close="answerLeave(false)" />
  </PageLayout>
</template>

<style scoped>
.list-controls { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.search-control { display: flex; flex: 1; align-items: center; gap: 10px; min-width: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.search-control svg { color: var(--muted); }
.tickets .search-control input { flex: 1; min-width: 0; width: 100%; padding: 0; border: 0; border-radius: 0; background: transparent; font-size: .9em; }
.sort-control { min-width: 0; }
.tickets .sort-control select { max-width: 180px; padding: 10px; font-size: .8em; color: var(--muted); }
.status-filters :deep(.segmented) { flex-wrap: wrap; gap: 6px; border: 0; padding: 0; border-radius: 0; background: transparent; overflow: visible; }
.status-filters :deep(button.segment) { padding: 6px 12px; border: 1px solid var(--border); font-size: .75em; }
.status-filters :deep(button.segment.active) { border-color: var(--accent); }
.ticket-workspace { display: grid; grid-template-columns: 300px minmax(0, 1fr); flex: 1; min-height: 0; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.ticket-browser { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; padding: 18px 12px; border-right: 1px solid var(--border); background: color-mix(in srgb, var(--surface) 45%, var(--bg)); }
.list-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 0 10px 14px; color: var(--muted); font-size: .75em; }
.list-heading > :first-child { text-transform: uppercase; letter-spacing: .08em; }
.list { display: flex; flex-direction: column; gap: 5px; margin: 0; padding: 0; list-style: none; }
.ticket-row { display: flex; flex-direction: column; gap: 8px; width: 100%; padding: 15px 12px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--text); font: inherit; text-align: left; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
.ticket-row:hover:not(:disabled) { background: var(--surface); }
.ticket-row.active { background: var(--bg); border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); box-shadow: inset 3px 0 var(--accent); }
.ticket-row:disabled { opacity: .65; cursor: default; }
.row-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; color: var(--muted); font-size: .7em; }
.title { font-size: .9em; font-weight: 600; line-height: 1.6; overflow-wrap: anywhere; }
.badge { padding: 1px 6px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: .9em; color: var(--muted); }
.unread-label { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); font-size: .75em; font-weight: 500; }
.status { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: .75em; }
.row-time { font-size: .7em; overflow-wrap: anywhere; }
svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.status svg, .unread-label svg { width: 14px; height: 14px; }
.list-footer { margin: auto 10px 0; padding-top: 24px; font-size: .75em; line-height: 1.8; }
.empty-message { margin: 8px 10px; font-size: .9em; }
.load-error { margin: 0 10px 12px; font-size: .85em; overflow-wrap: anywhere; }
.load-error p { margin: 0 0 8px; }
.ticket-thread { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--bg); }
.detail-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 24px; border-bottom: 1px solid var(--border); color: var(--muted); font-size: .75em; flex-shrink: 0; }
.detail-head > .status { font-size: 1em; margin-left: auto; }
.close { border: 0; padding: 2px 6px; border-radius: var(--radius-md); background: transparent; color: var(--muted); font: inherit; font-size: 1.8em; cursor: pointer; }
.detail-error { flex-shrink: 0; max-height: 25%; overflow: auto; margin: 12px 20px 0; font-size: .85em; overflow-wrap: anywhere; }
.conversation { flex: 1; min-height: 0; overflow: auto; padding: 24px 30px; overflow-wrap: anywhere; }
.detail-title { margin: 0 0 10px; font-size: 1.5em; font-weight: 600; line-height: 1.4; letter-spacing: -.02em; }
.filed { margin: 0 0 20px; font-size: .75em; }
.timeline { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; padding: 0; margin: 0 0 24px; list-style: none; font-size: .75em; }
.timeline li { display: flex; flex-direction: column; gap: 5px; border-top: 2px solid var(--border); padding-top: 9px; color: var(--muted); }
.timeline li.reached { border-color: var(--accent); }
.timeline li[aria-current="step"] > span { color: var(--text); font-weight: 600; }
.timeline time { font-size: .9em; overflow-wrap: anywhere; }
.original-report { margin-bottom: 22px; }
.text { margin: 8px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.85; font-size: .9em; }
.who { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px 12px; font-size: .75em; }
.who b { font-weight: 600; }
.who .muted { font-size: .9em; }
.conversation-label { margin: 0 0 14px; font-size: .75em; }
.thread { display: flex; flex-direction: column; gap: 16px; margin: 0; padding: 0; list-style: none; }
.thread li { padding: 14px 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); }
.thread li.support { background: var(--surface); }
.thread li.support .who b { color: var(--accent); }
.thread li.system { font-size: .9em; color: var(--muted); border-style: dashed; }
.form { display: flex; flex-direction: column; gap: 10px; }
.form label { display: flex; flex-direction: column; gap: 5px; font-size: .9em; }
.form textarea, .form input { width: 100%; min-width: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; resize: vertical; }
.character-count { color: var(--muted); font-size: .8em; text-align: right; }
.reply { flex-shrink: 0; padding: 16px 24px; border-top: 1px solid var(--border); }
.reply textarea { min-height: 64px; max-height: 140px; line-height: 1.6; font-size: .9em; }
.actions { display: flex; justify-content: flex-end; align-items: center; gap: 12px; }
.reply .actions { justify-content: space-between; }
.reply .manage-ticket { border-color: transparent; padding-left: 0; }
.send-reply { min-width: 76px; min-height: 40px; }
.thread-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 28px; color: var(--muted); text-align: center; }
.thread-placeholder svg { width: 34px; height: 34px; color: var(--accent); }
.thread-placeholder h3 { margin: 0; color: var(--text); font-size: 1.05em; font-weight: 600; }
.thread-placeholder p { margin: 0; font-size: .9em; }
.notice { flex-shrink: 0; max-height: 20%; overflow: auto; margin: 0 0 12px; color: var(--muted); font-size: .85em; }
.mobile-back { display: none; }
.new-ticket { min-height: 40px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
.tickets button:focus-visible, .tickets input:focus-visible, .tickets select:focus-visible, .tickets textarea:focus-visible, .conversation:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button[aria-busy="true"]::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 6px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); vertical-align: -1px; animation: ticket-spin .7s linear infinite; }
@keyframes ticket-spin { to { transform: rotate(360deg); } }
@media (max-width: 1000px) and (min-width: 768px) { .ticket-workspace { grid-template-columns: 240px minmax(0, 1fr); } .conversation { padding: 22px; } .detail-head, .reply { padding-inline: 20px; } }
@media (max-width: 767px) {
  .tickets :deep(.page-column) { padding: 20px 16px 12px; }
  .tickets :deep(.page-head) { flex-direction: row; align-items: flex-start; gap: 12px; margin-bottom: 18px; }
  .tickets :deep(.page-actions) { flex-shrink: 0; }
  .tickets :deep(.page-description) { max-width: 210px; }
  .tickets.thread-open :deep(.page-head-copy), .tickets.thread-open :deep(.page-toolbar) { display: none; }
  .tickets.thread-open :deep(.page-actions) { flex: 1; justify-content: space-between; align-items: center; }
  .mobile-back { display: inline-block; min-height: 44px; }
  .new-ticket { min-height: 44px; }
  .list-controls { gap: 8px; }
  .tickets .sort-control select { max-width: 135px; padding-inline: 7px; min-height: 44px; }
  .tickets .search-control input { font-size: max(1em, 16px); }
  .status-filters :deep(button.segment) { min-height: 44px; padding-inline: 9px; }
  .ticket-workspace { grid-template-columns: minmax(0, 1fr); }
  .ticket-browser { border-right: 0; padding: 16px 12px; }
  .ticket-workspace.reading .ticket-browser, .ticket-workspace:not(.reading) .thread-placeholder { display: none; }
  .list { gap: 0; }
  .ticket-row { padding: 18px 0; border: 0; border-bottom: 1px solid var(--border); border-radius: 0; }
  .ticket-row.active { box-shadow: none; background: transparent; }
  .title { font-size: .95em; }
  .detail-head { padding: 12px 18px; }
  .detail-head .close { display: none; }
  .conversation { padding: 20px; }
  .detail-title { font-size: 1.4em; }
  .reply { padding: 12px 16px; }
  .reply textarea { font-size: max(1em, 16px); }
  .reply button { min-height: 44px; }
  dialog.new-ticket-modal { position: fixed; inset: auto 0 var(--rail-height); width: 100%; max-width: none; max-height: calc(100dvh - var(--rail-height) - env(safe-area-inset-top, 0px) - 16px); margin: 0; padding: 22px 20px; border-radius: var(--radius-xl) var(--radius-xl) 0 0; }
  .new-ticket-modal .form input, .new-ticket-modal .form textarea { font-size: max(1em, 16px); }
  .new-ticket-modal .actions button { min-height: 44px; }
  .new-ticket-modal .actions .primary { flex: 1; }
}
</style>
