<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { adminClient, type Invite } from "../../api/AdminClient";
import { errorMessage, formatUtc } from "../../utils/errors";
import BaseModal from "../BaseModal.vue";
import ConfirmModal from "./ConfirmModal.vue";
import "./admin.css";

/** The overview counts (OverviewView) change whenever an invite does. */
const emit = defineEmits<{ changed: [] }>();
type EmailStatus = { kind: "checking" | "ready" } | { kind: "blocked"; reason: string };
const statusUnavailable = "Armory could not be reached. Check that Armory is running and Portcullis can call it.";
const createOpen = ref(false);
const emailStatus = ref<EmailStatus>({ kind: "checking" });
let emailCheck = 0;
const invites = ref<Invite[]>([]);
const listError = ref("");
const inviteeEmail = ref("");
const emailInput = ref<HTMLInputElement | null>(null);
const creating = ref(false);
const createError = ref("");
const sentTo = ref("");
const pendingRevoke = ref<Invite | null>(null);
const revoking = ref(false);

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
  createOpen.value = true;
  void checkEmailStatus();
}

defineExpose({ openCreate });

async function loadInvites(): Promise<void> {
  listError.value = "";
  try {
    invites.value = await adminClient.listInvites();
  } catch (err) {
    listError.value = errorMessage(err);
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
  if (!invite) return "";
  return `Revoke ${invite.invitee_email ?? "this invite"}? Its code stops working.`;
});

async function confirmRevoke(): Promise<void> {
  const invite = pendingRevoke.value;
  if (!invite) return;
  listError.value = "";
  revoking.value = true;
  try {
    await adminClient.revokeInvite(invite.id);
    invites.value = invites.value.filter((i) => i.id !== invite.id);
    emit("changed");
  } catch (err) {
    listError.value = errorMessage(err);
  } finally {
    revoking.value = false;
    pendingRevoke.value = null;
  }
}

onMounted(loadInvites);
</script>

<template>
  <div class="admin-panel">
    <BaseModal class="card invite-create admin-panel" :open="createOpen" title="Invite member" side @close="!creating && (createOpen = false)">
      <p class="muted">We email a one-time code. It works for 7 days. The person must register with this email address.</p>
      <form class="row-form" @submit.prevent="createInvite">
        <label for="invite-member-email">Email of the new member</label>
        <input id="invite-member-email" ref="emailInput" v-model="inviteeEmail" type="email" required :disabled="creating" />
        <p v-if="emailStatus.kind === 'checking'" class="muted" role="status">Checking email availability…</p>
        <template v-else-if="emailStatus.kind === 'blocked'">
          <p class="error" role="alert">{{ emailStatus.reason }}</p>
          <button type="button" class="small" @click="checkEmailStatus">Check again</button>
        </template>
        <p v-if="createError" class="error" role="alert">{{ createError }}</p>
        <button type="submit" class="primary" :disabled="!canSend" :aria-busy="creating">
          {{ creating ? "Sending ..." : "Send invite" }}
        </button>
      </form>
      <div v-if="sentTo" class="created" role="status">
        <p>Invitation sent to {{ sentTo }}.</p>
      </div>
    </BaseModal>

    <h3>Open invites</h3>
    <p v-if="listError" class="error">error: {{ listError }}</p>
    <p v-if="invites.length === 0 && !listError" class="muted">No open invites.</p>
    <div v-if="invites.length" class="table-wrap">
      <table>
        <thead>
          <tr><th>Invitee</th><th>Created</th><th>Expires</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="i in invites" :key="i.id">
            <td class="invitee">{{ i.invitee_email ?? "-" }}</td>
            <td>{{ formatUtc(i.created_at) }}</td>
            <td>{{ formatUtc(i.expires_at) }}</td>
            <td>
              <button type="button" class="small danger" @click="pendingRevoke = i">Revoke</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

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
.invite-create.side-modal.card { margin: 0; padding: 24px; background: var(--bg); }
.invite-create.side-modal .row-form { flex-direction: column; align-items: stretch; }
.invite-create.side-modal .row-form input { flex: none; width: 100%; }
.invite-create.side-modal .row-form .primary { align-self: flex-start; }
.invite-create > p {
  margin: 0;
  font-size: 0.9em;
}
.invite-create .row-form {
  margin-top: 18px;
  gap: 14px;
}
.invite-create .row-form p {
  margin: 0;
}
.invite-create .row-form button {
  align-self: flex-start;
}
.table-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.created {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.created p {
  margin: 0.3em 0;
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9em;
}
th,
td {
  padding: 14px 16px;
  border-top: 1px solid var(--border);
  text-align: left;
}
th {
  border-top: none;
  font-size: 0.85em;
  font-weight: 500;
  color: var(--muted);
  background: var(--surface);
}
.invitee {
  overflow-wrap: anywhere;
}
</style>
