<script setup lang="ts">
import ActionMessage from "./ActionMessage.vue";
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  adminClient,
  type AccountStatus,
  type AdminAccount,
  type Role,
} from "../../api/AdminClient";
import { useAuthStore } from "../../stores/auth";
import { errorMessage } from "../../utils/errors";
import AccountDrawer, { type AccountDraft } from "./AccountDrawer.vue";
import AdminSearch from "./AdminSearch.vue";
import PanelHelp from "./PanelHelp.vue";
import ConfirmModal from "./ConfirmModal.vue";
import RecordDrawer from "./RecordDrawer.vue";
import StatusFilters from "./StatusFilters.vue";
import "./admin.css";

/** The account roster: a status filter and a local search over username, email and role names, a
 * row that opens the account in a drawer, and a staged edit (profile fields plus role choices by ID)
 * saved sequentially through the existing endpoints. */
const props = defineProps<{ filters?: { q: string; status: AccountStatus } }>();
const emit = defineEmits<{ changed: []; filter: [value: { q: string; status: AccountStatus }] }>();

const STATUS_OPTIONS = [
  { id: "all", label: "All", tone: "accent" },
  { id: "unverified", label: "Unverified", tone: "warning" },
  { id: "disabled", label: "Disabled", tone: "muted" },
] as const;

type Pending = { kind: "disable"; account: AdminAccount } | { kind: "delete"; account: AdminAccount };

const auth = useAuthStore();

const accounts = ref<AdminAccount[]>([]);
/** Every account seen, by ID, so the open one survives a filter that no longer lists it. */
const known = ref<Map<number, AdminAccount>>(new Map());
const roles = ref<Role[]>([]);
const search = ref(props.filters?.q ?? "");
const status = ref<AccountStatus>(props.filters?.status ?? "all");
const loading = ref(true);
const loadError = ref("");
const actionError = ref("");
const notice = ref("");
const busy = ref(false);
const selectedId = ref<number | null>(null);
const pending = ref<Pending | null>(null);
const editing = ref(false);
const draft = ref<AccountDraft>({ username: "", email: "", roleIds: [] });
/** Role IDs held when editing began: only these may be removed by this edit. */
const snapshotRoleIds = ref<number[]>([]);
/** A failed save may have been applied by the server: re-read the account before retrying. */
let refreshBeforeRetry = false;
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const searchField = ref<InstanceType<typeof AdminSearch>>();

const myId = computed(() => auth.account?.id ?? null);
type RowStatus = "active" | "unverified" | "disabled";
const statusOf = (a: AdminAccount): RowStatus => !a.is_active ? "disabled" : !a.email_verified ? "unverified" : "active";
/** What each status means and what to do about it, shown in the helper popover beside the status. */
const STATUS_HELP: Record<RowStatus, string> = {
  active: "The user can sign in. Nothing to do.",
  unverified: "The email address is not confirmed yet, so sign-in is held back. Ask the person to open the verification link in their email, or invite them again.",
  disabled: "The user cannot sign in. Open the user and turn Active on to let the person back in.",
};
const selected = computed(() => (selectedId.value === null ? null : known.value.get(selectedId.value) ?? null));
const canEdit = computed(() => !!selected.value && !selected.value.is_protected && (auth.hasPermission("accounts.manage") || auth.hasPermission("roles.assign")));

const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return accounts.value;
  return accounts.value.filter((a) => [a.username, a.email, ...a.roles.map((r) => r.name)].some((value) => value.toLowerCase().includes(query)));
});

function remember(list: AdminAccount[]): void {
  const next = new Map(known.value);
  for (const account of list) next.set(account.id, account);
  known.value = next;
}

// Only the newest roster request may fill the table: a slow answer to an earlier status would
// otherwise overwrite it.
let loadSeq = 0;
async function loadAccounts(): Promise<void> {
  const seq = ++loadSeq;
  loading.value = true;
  try {
    const rows = await adminClient.listAccounts({ status: status.value });
    if (seq !== loadSeq) return;
    accounts.value = rows;
    remember(rows);
    loadError.value = "";
  } catch (err) {
    if (seq === loadSeq) loadError.value = errorMessage(err);
  } finally {
    if (seq === loadSeq) loading.value = false;
  }
}

async function loadRoles(): Promise<void> {
  try {
    roles.value = ["roles.view", "roles.manage", "roles.assign"].some(auth.hasPermission) ? await adminClient.listRoles() : [];
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

watch(status, loadAccounts);
watch(() => props.filters, (next) => {
  if (next) { search.value = next.q; status.value = next.status; }
});
watch([search, status], () => emit("filter", { q: search.value, status: status.value }));
onMounted(() => {
  void loadAccounts();
  void loadRoles();
});

function replace(updated: AdminAccount): void {
  accounts.value = accounts.value.map((a) => (a.id === updated.id ? updated : a));
  remember([updated]);
}

function select(account: AdminAccount): void {
  selectedId.value = account.id;
  actionError.value = "";
  notice.value = "";
  editing.value = false;
}

function closeDrawer(): void {
  selectedId.value = null;
  editing.value = false;
  actionError.value = "";
}

function startEdit(): void {
  const account = selected.value;
  if (!account) return;
  draft.value = { username: account.username, email: account.email, roleIds: account.roles.map((r) => r.id) };
  snapshotRoleIds.value = account.roles.map((r) => r.id);
  actionError.value = "";
  notice.value = "";
  refreshBeforeRetry = false;
  editing.value = true;
}

/** Validates the profile fields before the save confirmation opens. */
function requestSave(): void {
  const form = document.getElementById("account-editor") as HTMLFormElement | null;
  if (form && !form.reportValidity()) return;
  drawer.value?.requestSave();
}

function discard(): void {
  editing.value = false;
  actionError.value = "";
}

/** Refreshes the signed-in account when it was the one changed, so the nav and header follow. */
async function refreshSelf(id: number): Promise<void> {
  if (id === myId.value) await auth.refresh();
}

/** The saved changes still outstanding: profile fields first, then role additions, then removals. */
function outstanding(account: AdminAccount) {
  const changes: { username?: string; email?: string } = {};
  if (auth.hasPermission("accounts.manage")) {
    if (draft.value.username.trim() !== account.username) changes.username = draft.value.username.trim();
    if (draft.value.email.trim() !== account.email) changes.email = draft.value.email.trim();
  }
  const held = new Set(account.roles.map((r) => r.id));
  const wanted = new Set(draft.value.roleIds);
  const canAssign = auth.hasPermission("roles.assign");
  const adds = canAssign ? draft.value.roleIds.filter((id) => !held.has(id)) : [];
  const removes = canAssign ? snapshotRoleIds.value.filter((id) => !wanted.has(id) && held.has(id)) : [];
  return { changes, adds, removes };
}

const roleName = (id: number) => roles.value.find((r) => r.id === id)?.name ?? selected.value?.roles.find((r) => r.id === id)?.name ?? `role ${id}`;

async function save(): Promise<void> {
  const target = selected.value;
  if (!target || busy.value) return;
  actionError.value = "";
  notice.value = "";
  busy.value = true;
  let confirmedWrite = false;
  let step = "";
  try {
    let account = target;
    if (refreshBeforeRetry) {
      // The earlier failure was ambiguous: re-read through the roster endpoint, then skip what already landed.
      step = "refreshing the account";
      const fresh = (await adminClient.listAccounts()).find((a) => a.id === target.id);
      if (!fresh) throw new Error("The account no longer exists.");
      replace(fresh);
      account = fresh;
      refreshBeforeRetry = false;
    }
    const { changes, adds, removes } = outstanding(account);
    if (Object.keys(changes).length) {
      step = "saving profile details";
      account = await adminClient.updateAccount(account.id, changes);
      replace(account);
      confirmedWrite = true;
    }
    for (const id of adds) {
      step = `adding ${roleName(id)}`;
      account = await adminClient.assignRole(account.id, id);
      replace(account);
      confirmedWrite = true;
    }
    for (const id of removes) {
      step = `removing ${roleName(id)}`;
      account = await adminClient.removeRole(account.id, id);
      replace(account);
      confirmedWrite = true;
    }
    editing.value = false;
    notice.value = "Changes saved.";
  } catch (err) {
    refreshBeforeRetry = true;
    actionError.value = `Could not finish ${step}: ${errorMessage(err)}`;
  } finally {
    busy.value = false;
    if (confirmedWrite) {
      try { await refreshSelf(target.id); } catch { /* the next request shows any lost session */ }
      emit("changed");
    }
  }
}

/** Runs one separate admin call, showing its error or notice. */
async function act(account: AdminAccount, call: () => Promise<void>, done?: string): Promise<void> {
  actionError.value = "";
  notice.value = "";
  busy.value = true;
  try {
    await call();
    if (done) notice.value = done;
    await refreshSelf(account.id);
    emit("changed");
  } catch (err) {
    actionError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

function setActive(account: AdminAccount, active: boolean): Promise<void> | undefined {
  if (!active) {
    pending.value = { kind: "disable", account };
    return;
  }
  return act(account, async () => replace(await adminClient.updateAccount(account.id, { is_active: true })));
}

function sendVerification(account: AdminAccount): Promise<void> {
  return act(account, async () => { await adminClient.sendVerification(account.id); }, `Verification email sent to ${account.email}.`);
}

const confirmText = computed(() => {
  const p = pending.value;
  if (!p) return { title: "", message: "", label: "", requireText: "" };
  const name = p.account.username;
  if (p.kind === "disable") return { title: "Disable user", message: `Disable '${name}'? They are logged out and can't log in until enabled.`, label: "Disable", requireText: "" };
  return { title: "Delete user", message: `Delete '${name}' permanently? This can't be undone.`, label: "Delete", requireText: name };
});

async function confirm(): Promise<void> {
  const p = pending.value;
  if (!p) return;
  const { account } = p;
  await act(account, async () => {
    if (p.kind === "disable") {
      replace(await adminClient.updateAccount(account.id, { is_active: false }));
    } else {
      await adminClient.deleteAccount(account.id);
      accounts.value = accounts.value.filter((a) => a.id !== account.id);
      known.value = new Map([...known.value].filter(([id]) => id !== account.id));
      closeDrawer();
    }
  });
  // On failure the dialog closes too; the error shows in the drawer.
  pending.value = null;
}
</script>

<template>
  <div class="accounts-panel admin-panel">
    <StatusFilters v-model="status" label="Filter by user status" :options="STATUS_OPTIONS" />
    <section class="admin-panel-card" aria-labelledby="account-roster">
      <header class="admin-panel-head">
        <h2 id="account-roster">User roster</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="User roster">Everyone who can sign in. Search by name, email or role, open a row to see details, change roles and save, or invite someone new. Disabled and unverified users have their own filters above.</PanelHelp>
          <RouterLink v-if="auth.hasPermission('invites.manage')" class="admin-icon accent" to="/admin/invites?create=1" aria-label="Invite member" title="Invite member"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M19 8v6M16 11h6" /></svg></RouterLink>
          <AdminSearch ref="searchField" v-model="search" label="Search users" />
        </div>
      </header>
      <ActionMessage v-if="loadError" kind="error" :text="loadError" class="admin-panel-text"><button type="button" class="chip" @click="loadAccounts">Retry</button></ActionMessage>
      <p v-else-if="loading && !accounts.length" class="admin-panel-text muted" role="status">Loading users…</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">{{ accounts.length ? "No users match your search." : "No users match this filter." }}
        <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button>
      </p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="account-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">User</th><th scope="col">Roles</th><th scope="col">Status</th></tr></thead>
          <tbody>
            <tr v-for="a in visible" :key="a.id" :data-id="a.id" data-test="account" :class="{ selected: a.id === selectedId }">
              <th scope="row">
                <div class="admin-record-name">
                  <span class="admin-record-badge" aria-hidden="true">{{ a.username.slice(0, 2).toUpperCase() }}</span>
                  <div>
                    <button type="button" class="admin-row-button" aria-haspopup="dialog" @click="select(a)">{{ a.username }}</button>
                    <span v-if="a.id === myId" class="badge">you</span>
                    <span v-if="a.is_protected" class="badge">protected</span>
                    <p>{{ a.email }}</p>
                    <div class="role-tags mobile-roles"><span v-for="r in a.roles" :key="r.id" class="role-tag">{{ r.name }}</span><span v-if="!a.roles.length" class="no-roles">No roles</span></div>
                  </div>
                </div>
              </th>
              <td class="role-cell"><div class="role-tags"><span v-for="r in a.roles" :key="r.id" class="role-tag">{{ r.name }}</span><span v-if="!a.roles.length" class="no-roles">No roles</span></div></td>
              <td><div class="status-cell">
                <span v-if="!a.is_active" class="account-status disabled"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 12h8M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0" /></svg>disabled</span>
                <span v-else-if="!a.email_verified" class="account-status unverified"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0" /></svg>unverified</span>
                <span v-else class="account-status active"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>active</span>
                <PanelHelp :title="statusOf(a)"><p>{{ STATUS_HELP[statusOf(a)] }}</p></PanelHelp>
              </div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!loadError && accounts.length" class="admin-panel-text muted count" role="status">{{ visible.length }} of {{ accounts.length }} {{ accounts.length === 1 ? "user" : "users" }}</p>
    </section>

    <RecordDrawer ref="drawer" :open="selected !== null" :title="selected ? `User ${selected.username}` : 'User details'"
      :editable="canEdit" :editing="editing" :busy="busy" :fallback-focus="() => searchField?.focus()"
      @edit="startEdit" @close="closeDrawer" @discard="discard" @save="save">
      <AccountDrawer v-if="selected" v-model:draft="draft" :account="selected" :roles="roles" :is-self="selected.id === myId" :busy="busy"
        :error="actionError" :notice="notice" :editing="editing"
        @set-active="(active) => setActive(selected!, active)" @send-verification="sendVerification(selected!)" @remove="pending = { kind: 'delete', account: selected! }" />
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="busy" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="button" class="primary" :disabled="busy" :aria-busy="busy" data-test="save-account" @click="requestSave">Save changes</button>
      </template>
    </RecordDrawer>

    <ConfirmModal
      :open="pending !== null"
      :title="confirmText.title"
      :message="confirmText.message"
      :confirm-label="confirmText.label"
      :require-text="confirmText.requireText"
      danger
      :busy="busy"
      @confirm="confirm"
      @close="pending = null"
    />
  </div>
</template>

<style scoped>
.status-cell { display: flex; align-items: center; gap: 4px; }
.accounts-panel { min-width: 0; }
.admin-records tbody tr.selected { background: var(--surface); }
.role-tags.mobile-roles { display: none; }
.admin-record-name p { overflow-wrap: anywhere; }
.badge { margin-inline-start: 6px; }
.role-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.role-tag { display: inline-flex; align-items: center; padding: 2px 9px; border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--surface); color: var(--text); font-size: 0.78em; font-weight: 400; white-space: nowrap; }
.no-roles { color: var(--muted); font-size: 0.85em; font-style: italic; }
.account-status { display: inline-flex; align-items: center; gap: 5px; padding: 2px 10px; border: 1px solid var(--border); border-radius: var(--radius-full); white-space: nowrap; font-size: 0.8em; text-transform: capitalize; }
.account-status.active { background: color-mix(in srgb, var(--success) 8%, var(--bg)); }
.account-status.unverified { background: color-mix(in srgb, var(--warning) 8%, var(--bg)); }
.account-status svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.account-status.active { color: var(--success); }
.account-status.unverified { color: var(--warning); }
.account-status.disabled { color: var(--muted); }
.count { border-top: 1px solid var(--border); font-size: 0.8rem; }
@media (max-width: 767px) {
  .role-cell, thead th:nth-child(2) { display: none; }
  .role-tags.mobile-roles { display: flex; margin-top: 6px; }
}
@media (max-width: 520px) { .status-cell :deep(.admin-icon) { display: none; } .admin-records :is(th, td):first-child { width: auto; } }
@media (max-width: 400px) { .admin-record-badge { display: none; } }
</style>
