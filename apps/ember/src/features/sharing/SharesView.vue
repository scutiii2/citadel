<script setup lang="ts">
import { PanelHelp } from "@citadel/ui";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import "@citadel/ui/infoPage.css";
import { PageLayout } from "@citadel/ui";
import { ConfirmModal } from "@citadel/ui";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../stores/auth";
import { errorMessage } from "../../utils/errors";
import { formatUtc } from "../../utils/time";
import { SHARE_NAME_MAX, type Share, type ShareKind, type ShareStatus } from "./api/SharingClient";
import ShareReview from "./components/ShareReview.vue";
import { useSharingStore } from "./stores/sharing";

/** Copies sent to the person and by the person. Reading, keeping, declining and blocking happen in the review dialog;
 * a waiting share can be withdrawn here; blocked accounts are listed and can be unblocked. */
const KIND: Record<ShareKind, string> = { file: "File", section: "Section", skill: "Skill", stack_item: "Short-term item" };
const STATUS: Record<ShareStatus, string> = { pending: "Waiting for an answer", accepted: "Kept", declined: "Declined", revoked: "Withdrawn", rejected: "Not approved" };

const store = useSharingStore();
const auth = useAuthStore();
const reviewing = ref<Share | null>(null);
const withdrawing = ref<Share | null>(null);
const notice = ref("");
const destination = ref<"notes" | "skills">();
const actionError = ref("");
const busy = ref(false);
const username = ref("");
const blockError = ref("");

let accountRun = 0;
function clear(): void {
  accountRun++;
  reviewing.value = withdrawing.value = null;
  notice.value = actionError.value = username.value = blockError.value = "";
  destination.value = undefined;
  busy.value = false;
}
onMounted(() => void store.load());
onBeforeUnmount(() => { clear(); store.forget(); });
watch(() => auth.account?.id, () => { clear(); void store.load(); }, { flush: "sync" });

function reviewed(message: string, page?: "notes" | "skills"): void {
  reviewing.value = null;
  notice.value = message;
  destination.value = page;
}

async function withdraw(): Promise<void> {
  const share = withdrawing.value;
  if (!share || busy.value) return;
  const run = accountRun;
  busy.value = true;
  actionError.value = "";
  try {
    await store.revoke(share.id);
    if (run === accountRun) reviewed("Share withdrawn.");
  } catch (err) {
    if (run === accountRun) actionError.value = errorMessage(err);
  } finally {
    if (run === accountRun) {
      busy.value = false;
      withdrawing.value = null;
    }
  }
}

async function block(): Promise<void> {
  const name = username.value.trim();
  if (!name || busy.value) return;
  const run = accountRun;
  busy.value = true;
  blockError.value = "";
  try {
    await store.block(name);
    if (run === accountRun) {
      username.value = "";
      reviewed("Account blocked. Its waiting shares were declined.");
    }
  } catch (err) {
    if (run === accountRun) blockError.value = errorMessage(err);
  } finally {
    if (run === accountRun) busy.value = false;
  }
}

async function unblock(uid: string): Promise<void> {
  if (busy.value) return;
  const run = accountRun;
  busy.value = true;
  blockError.value = "";
  try {
    await store.unblock(uid);
  } catch (err) {
    if (run === accountRun) blockError.value = errorMessage(err);
  } finally {
    if (run === accountRun) busy.value = false;
  }
}
</script>

<template>
  <PageLayout class="shares info-content" title="Shares">
    <template #actions><PanelHelp title="Shares">Copies of files, skills and memory items: what was sent to you and what you sent.</PanelHelp></template>
    <p v-if="notice" class="notice" role="status">
      {{ notice }}
      <RouterLink v-if="destination" class="notice-link" :to="{ name: destination }">{{ destination === "skills" ? "Go to Skills" : "Go to Notes" }}</RouterLink>
    </p>
    <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
    <StateMessage v-if="store.status === 'idle' || store.status === 'loading'" kind="loading">Loading …</StateMessage>
    <StateMessage v-else-if="store.status === 'error'" kind="error" @retry="store.load()">Could not load your shares: {{ store.error }}</StateMessage>
    <template v-else>
      <StateMessage v-if="store.error" kind="error" @retry="store.load()">Could not refresh: {{ store.error }}</StateMessage>

      <section aria-label="Waiting for you" class="block">
        <h3>Waiting for you</h3>
        <StateMessage v-if="store.inbox.length === 0" kind="empty">Nothing is waiting for you.</StateMessage>
        <ul v-else class="rows">
          <li v-for="share in store.inbox" :key="share.id" class="row">
            <div class="what">
              <span class="title">{{ share.title }}</span>
              <span class="muted">From {{ share.sender }} · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</span>
            </div>
            <button type="button" class="pill-btn primary" :disabled="busy" @click="reviewing = share">Review</button>
          </li>
        </ul>
      </section>

      <section aria-label="Sent by you" class="block">
        <h3>Sent by you</h3>
        <StateMessage v-if="store.sent.length === 0" kind="empty">You have not shared anything.</StateMessage>
        <ul v-else class="rows">
          <li v-for="share in store.sent" :key="share.id" class="row">
            <div class="what">
              <span class="title">{{ share.title }}</span>
              <span class="muted">To {{ share.recipient }} · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</span>
              <span class="status-badge">{{ STATUS[share.status] }}</span>
            </div>
            <button v-if="share.status === 'pending'" type="button" class="pill-btn ghost" :disabled="busy" @click="withdrawing = share">Withdraw</button>
          </li>
        </ul>
      </section>

      <section aria-label="Blocked accounts" class="block">
        <h3>Blocked accounts</h3>
        <p class="muted hint">A blocked account cannot send you shares. Blocking also declines what it already sent.</p>
        <StateMessage v-if="store.blocks.length === 0" kind="empty">You have not blocked anyone.</StateMessage>
        <ul v-else class="rows">
          <li v-for="entry in store.blocks" :key="entry.uid" class="row">
            <div class="what"><span class="title">{{ entry.username }}</span></div>
            <button type="button" class="pill-btn ghost" :disabled="busy" @click="unblock(entry.uid)">Unblock</button>
          </li>
        </ul>
        <form class="add" @submit.prevent="block">
          <input v-model="username" type="text" aria-label="Username to block" placeholder="Username to block" :maxlength="SHARE_NAME_MAX" autocomplete="off" :disabled="busy" />
          <button type="submit" class="pill-btn ghost" :disabled="busy || username.trim() === ''">Block</button>
        </form>
        <p v-if="blockError" class="error" role="alert">{{ blockError }}</p>
      </section>
    </template>

    <ShareReview v-if="reviewing" :share="reviewing" @close="reviewing = null" @done="reviewed" />
    <ConfirmModal
      class="withdraw-confirm"
      :open="withdrawing !== null"
      title="Withdraw this share?"
      message="They will no longer be able to keep it."
      confirm-label="Withdraw"
      danger
      :busy="busy"
      @confirm="withdraw"
      @close="withdrawing = null"
    />
  </PageLayout>
</template>

<style scoped>
.shares :deep(.error), .shares :deep(button.danger) { color: var(--text); }
.withdraw-confirm :deep(.bin), .withdraw-confirm :deep(.ring) { color: var(--danger); }
.block { display: flex; flex-direction: column; gap: 8px; margin-bottom: 28px; }
.block h3 { margin: 0; }
.hint, .notice { margin: 0; font-size: .85em; }
.notice-link { display: inline-flex; align-items: center; }
.rows { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
.what { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; min-width: 0; }
.title { font-weight: 600; overflow-wrap: anywhere; }
.what .muted { font-size: .85em; overflow-wrap: anywhere; }
.add { display: flex; gap: 8px; }
.add input { flex: 1; min-width: 0; }
@media (max-width: 767px) {
  .row { flex-direction: column; align-items: stretch; }
  .row button, .add button, .notice-link, .shares :deep(.state button), .withdraw-confirm :deep(.actions button) { min-height: 44px; min-width: 44px; }
  .add input { min-height: 44px; font-size: max(1em, 16px); }
}
</style>
