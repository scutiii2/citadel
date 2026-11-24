<script setup lang="ts">
import ActionMessage from "./ActionMessage.vue";
import { computed, onMounted, ref } from "vue";
import { adminClient, type Invite } from "../../api/AdminClient";
import { errorMessage, formatUtc } from "../../utils/errors";
import AdminSearch from "./AdminSearch.vue";
import PanelHelp from "./PanelHelp.vue";
import ConfirmModal from "./ConfirmModal.vue";
import RecordDrawer from "./RecordDrawer.vue";
import "./admin.css";

/** Open invites: a searchable roster whose rows open an invite's details (with Revoke), and a create
 * drawer for the email invite. The overview counts (OverviewView) change whenever an invite does. */
const emit = defineEmits<{ changed: [] }>();

type EmailStatus = { kind: "checking" | "ready" } | { kind: "blocked"; reason: string };
const statusUnavailable = "Armory could not be reached. Check that Armory is running and Portcullis can call it.";

const createOpen = ref(false);
const emailStatus = ref<EmailStatus>({ kind: "checking" });
let emailCheck = 0;

const invites = ref<Invite[]>([]);
const loading = ref(true);
const listError = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const selectedId = ref<number | null>(null);
const inviteeEmail = ref("");
const emailInput = ref<HTMLInputElement | null>(null);
const creating = ref(false);
const createError = ref("");
const sentTo = ref("");
const pendingRevoke = ref<Invite | null>(null);
const revoking = ref(false);
const revokeError = ref("");

const selected = computed(() => invites.value.find((i) => i.id === selectedId.value) ?? null);
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return invites.value.filter((i) => [i.invitee_email ?? "", i.delivery_method].some((text) => text.toLowerCase().includes(query)));
});
const canSend = computed(() => (
  emailStatus.value.kind === "ready" && !creating.value
  && inviteeEmail.value.trim() !== "" && emailInput.value?.validity.valid === true
));

async function checkEmailStatus(): Promise<void> {
  const check = ++emailCheck;
  emailStatus.value = { kind: "checking" };
  createError.value = "";
  let status: EmailStatus;
  try {
    const result = await adminClient.inviteEmailStatus();
    status = result.ready ? { kind: "ready" } : { kind: "blocked", reason: result.reason ?? statusUnavailable };
  } catch {
    status = { kind: "blocked", reason: statusUnavailable };
  }
  if (check === emailCheck) emailStatus.value = status;
}

function openCreate(): void {
  inviteeEmail.value = "";
  sentTo.value = "";
  createError.value = "";
  selectedId.value = null;
  createOpen.value = true;
  void checkEmailStatus();
}
defineExpose({ openCreate });

async function loadInvites(): Promise<void> {
  listError.value = "";
  loading.value = true;
  try {
    invites.value = await adminClient.listInvites();
  } catch (err) {
    listError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function createInvite(): Promise<void> {
  if (!canSend.value) return;
  createError.value = "";
  sentTo.value = "";
  creating.value = true;
  try {
    const email = inviteeEmail.value.trim();
    const invite = await adminClient.createInvite(email);
    sentTo.value = invite.invitee_email ?? email;
    inviteeEmail.value = "";
    emit("changed");
    await loadInvites();
  } catch (err) {
    createError.value = errorMessage(err);
  } finally {
    creating.value = false;
  }
}

const revokeMessage = computed(() => {
  const invite = pendingRevoke.value;
  return invite ? `Revoke ${invite.invitee_email ?? "this invite"}? Its code stops working.` : "";
});

async function confirmRevoke(): Promise<void> {
  const invite = pendingRevoke.value;
  if (!invite) return;
  revokeError.value = "";
  revoking.value = true;
  try {
    await adminClient.revokeInvite(invite.id);
    invites.value = invites.value.filter((i) => i.id !== invite.id);
    if (selectedId.value === invite.id) selectedId.value = null;
    emit("changed");
  } catch (err) {
    revokeError.value = errorMessage(err);
  } finally {
    revoking.value = false;
    pendingRevoke.value = null;
  }
}

onMounted(loadInvites);
</script>

<template>
  <div class="invites-panel admin-panel">
    <section class="admin-panel-card" aria-labelledby="invite-roster">
      <header class="admin-panel-head">
        <h2 id="invite-roster">Open invites</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Open invites"><p>Invitations that have been sent and not used yet. Open one to copy its link or revoke it.</p><p>Invites work once and expire after 7 days. New users receive the configured default role.</p></PanelHelp>
          <button type="button" class="admin-icon accent" data-test="invite-member" aria-label="Invite member" title="Invite member" @click="openCreate"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19 8v6M16 11h6" /></svg></button>
          <AdminSearch ref="searchField" v-model="search" label="Search invites" />
        </div>
      </header>
      <ActionMessage v-if="listError" kind="error" :text="listError" class="admin-panel-text"><button type="button" class="chip" @click="loadInvites">Retry</button></ActionMessage>
      <p v-else-if="loading" class="admin-panel-text muted" role="status">Loading invites…</p>
      <p v-else-if="!invites.length" class="admin-panel-text muted">No open invites.</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">No invites match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="invite-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">Invitee</th><th scope="col">Created</th><th scope="col">Expires</th></tr></thead>
          <tbody>
            <tr v-for="i in visible" :key="i.id" :data-id="i.id" data-test="invite" :class="{ selected: i.id === selectedId }">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="selectedId = i.id; revokeError = ''">{{ i.invitee_email ?? "-" }}</button></th>
              <td>{{ formatUtc(i.created_at) }}</td>
              <td>{{ formatUtc(i.expires_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!loading && !listError && invites.length" class="admin-panel-text muted count" role="status">{{ visible.length }} of {{ invites.length }} invites</p>
    </section>

    <RecordDrawer :open="selected !== null" :title="selected ? `Invite ${selected.invitee_email ?? ''}`.trim() : 'Invite details'" :fallback-focus="() => searchField?.focus()" @close="selectedId = null">
      <div v-if="selected" class="admin-details">
        <dl>
          <dt>Invitee</dt><dd>{{ selected.invitee_email ?? "-" }}</dd>
          <dt>Delivery</dt><dd>{{ selected.delivery_method === "email" ? "Email" : "Manual" }}</dd>
          <dt>Created</dt><dd>{{ formatUtc(selected.created_at) }}</dd>
          <dt>Expires</dt><dd>{{ formatUtc(selected.expires_at) }}</dd>
        </dl>
        <ActionMessage v-if="revokeError" kind="error" :text="revokeError" />
        <section class="danger-zone">
          <h4>Danger zone</h4>
          <p class="muted">Revoking stops the invite's code from working. This can't be undone.</p>
          <button type="button" class="danger" data-test="revoke" @click="pendingRevoke = selected">Revoke invite</button>
        </section>
      </div>
    </RecordDrawer>

    <RecordDrawer :open="createOpen" title="Invite member" :editing="inviteeEmail.trim() !== ''" :busy="creating" :fallback-focus="() => searchField?.focus()" @close="createOpen = false" @discard="inviteeEmail = ''">
      <p class="muted">We email a one-time code. It works for 7 days. The person must register with this email address.</p>
      <form id="invite-create" class="admin-editor" @submit.prevent="createInvite">
        <label for="invite-member-email">Email of the new member</label>
        <input id="invite-member-email" ref="emailInput" v-model="inviteeEmail" type="email" required :disabled="creating" />
        <p v-if="emailStatus.kind === 'checking'" class="muted" role="status">Checking email availability…</p>
        <template v-else-if="emailStatus.kind === 'blocked'">
          <ActionMessage kind="error" :text="emailStatus.reason" />
          <button type="button" class="chip" @click="checkEmailStatus">Check again</button>
        </template>
        <ActionMessage v-if="createError" kind="error" :text="createError" />
      </form>
      <ActionMessage v-if="sentTo" kind="ok" :text="`Invitation sent to ${sentTo}.`" class="created" />
      <template #footer>
        <button type="button" class="chip" :disabled="creating" @click="createOpen = false">Close</button>
        <button type="submit" form="invite-create" class="primary" :disabled="!canSend" :aria-busy="creating">{{ creating ? "Sending ..." : "Send invite" }}</button>
      </template>
    </RecordDrawer>

    <ConfirmModal
      :open="pendingRevoke !== null"
      title="Revoke invite"
      :message="revokeMessage"
      confirm-label="Revoke"
      danger
      :busy="revoking"
      @confirm="confirmRevoke"
      @close="pendingRevoke = null"
    />
  </div>
</template>

<style scoped>
.invites-panel { min-width: 0; }
.admin-records tbody tr.selected { background: var(--surface); }
.admin-editor { max-width: none; }
.created { margin-top: 14px; }
.count { border-top: 1px solid var(--border); font-size: 0.8rem; }
.danger-zone { margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--border); }
.danger-zone h4 { margin: 0 0 8px; font-size: 0.85em; }
</style>
