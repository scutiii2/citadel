<script setup lang="ts">
import ActionMessage from "./ActionMessage.vue";
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { adminClient, type AdminAccount, type PermissionInfo, type Role } from "../../api/AdminClient";
import { useAuthStore } from "../../stores/auth";
import { errorMessage } from "../../utils/errors";
import AdminSearch from "./AdminSearch.vue";
import PanelHelp from "./PanelHelp.vue";
import ConfirmModal from "./ConfirmModal.vue";
import RecordDrawer from "./RecordDrawer.vue";
import RoleEditor from "./RoleEditor.vue";
import "./admin.css";

/** The role roster: a searchable list whose rows open the role in a drawer for details and editing.
 * Creation opens in the same drawer. The draft lives in `RoleEditor`; this panel asks before saving or
 * discarding it, and guards a route change or page unload while it holds unsaved edits. */
const auth = useAuthStore();
const roles = ref<Role[]>([]);
const permissions = ref<PermissionInfo[]>([]);
const search = ref("");
const loading = ref(true);
const selectedId = ref<number | null>(null);
const loadError = ref("");
const actionError = ref("");
const busy = ref(false);
const saved = ref(false);
const editing = ref(false);
const roleEditor = ref<InstanceType<typeof RoleEditor> | null>(null);
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const createDrawer = ref<InstanceType<typeof RecordDrawer>>();
const searchField = ref<InstanceType<typeof AdminSearch>>();
const dirty = ref(false);

const discardOpen = ref(false);
let discardAnswer: ((value: boolean) => void) | null = null;

/** Asks before a route change drops unsaved edits; true when the caller may go on. */
function confirmDiscard(): Promise<boolean> {
  if (busy.value) return Promise.resolve(false);
  if (!dirty.value && !newRole.name && !newRole.description) return Promise.resolve(true);
  if (discardAnswer) return Promise.resolve(false);
  discardOpen.value = true;
  return new Promise((resolve) => { discardAnswer = resolve; });
}

function answerDiscard(discard: boolean): void {
  if (discard) { roleEditor.value?.revert(); dirty.value = false; editing.value = false; creating.value = false; }
  discardOpen.value = false;
  discardAnswer?.(discard);
  discardAnswer = null;
}

function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value) { event.preventDefault(); event.returnValue = ""; }
}

const affected = reactive<{ loading: boolean; error: string; accounts: AdminAccount[] | null }>({ loading: false, error: "", accounts: null });
async function showAccounts(): Promise<void> {
  const role = selected.value;
  if (!role) return;
  affected.loading = true;
  affected.error = "";
  try {
    const accounts = await adminClient.listAccounts();
    if (selected.value?.id === role.id) affected.accounts = accounts.filter((a) => a.roles.some((r) => r.id === role.id));
  } catch (err) {
    affected.error = errorMessage(err);
  } finally {
    affected.loading = false;
  }
}

const pendingDelete = ref<Role | null>(null);
const creating = ref(false);
const newRole = reactive({ name: "", description: "", error: "", saving: false });
const selected = computed(() => roles.value.find((r) => r.id === selectedId.value) ?? null);
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return roles.value.filter((r) => [r.name, r.description ?? ""].some((text) => text.toLowerCase().includes(query)));
});
const canEdit = computed(() => !!selected.value && auth.hasPermission("roles.manage") && selected.value.permissions.every(auth.hasPermission));

async function load(): Promise<void> {
  loadError.value = "";
  loading.value = true;
  try {
    [roles.value, permissions.value] = await Promise.all([adminClient.listRoles(), adminClient.listPermissions()]);
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function replace(updated: Role): void {
  roles.value = roles.value.map((r) => (r.id === updated.id ? updated : r));
}

function select(role: Role): void {
  selectedId.value = role.id;
  actionError.value = "";
  saved.value = false;
  editing.value = false;
  affected.accounts = null;
  affected.error = "";
}

function closeDrawer(): void {
  selectedId.value = null;
  editing.value = false;
  creating.value = false;
  dirty.value = false;
  actionError.value = "";
}

/** Runs one admin call for `role`. When the logged-in account holds the role, its permissions may
 * have changed, so the account is re-read. */
async function act(role: Role, call: () => Promise<void>): Promise<boolean> {
  actionError.value = "";
  saved.value = false;
  busy.value = true;
  const held = auth.account?.roles.includes(role.name) ?? false;
  try {
    await call();
    if (held) await auth.refresh();
    saved.value = true;
    return true;
  } catch (err) {
    actionError.value = errorMessage(err);
    return false;
  } finally {
    busy.value = false;
  }
}

function openCreate(): void {
  Object.assign(newRole, { name: "", description: "", error: "" });
  selectedId.value = null;
  creating.value = true;
}
defineExpose({ openCreate, confirmDiscard });

async function createRole(): Promise<void> {
  newRole.error = "";
  newRole.saving = true;
  try {
    const role = await adminClient.createRole(newRole.name.trim(), newRole.description.trim() || null);
    roles.value = [...roles.value, role].sort((a, b) => a.name.localeCompare(b.name));
    creating.value = false;
    select(role);
  } catch (err) {
    newRole.error = errorMessage(err);
  } finally {
    newRole.saving = false;
  }
}

/** Validates the open form, then asks the drawer for its save confirmation. */
function requestSave(formId: string, target: InstanceType<typeof RecordDrawer> | undefined): void {
  const form = document.getElementById(formId) as HTMLFormElement | null;
  if (form && !form.reportValidity()) return;
  target?.requestSave();
}

async function saveRole(): Promise<void> {
  const role = selected.value;
  const draft = roleEditor.value;
  if (!role || !draft || !draft.dirty) { editing.value = false; return; }
  const ok = await act(role, async () => replace(await adminClient.updateRole(role.id, draft.changes)));
  if (ok) editing.value = false;
}

function discardEdit(): void {
  roleEditor.value?.revert();
  editing.value = false;
  actionError.value = "";
}

const deleteMessage = computed(() => {
  const role = pendingDelete.value;
  if (!role) return "";
  const users = role.account_count === 1 ? "1 user" : `${role.account_count} users`;
  return `Delete role '${role.name}'? It is removed from ${users}.`;
});

async function confirmDelete(): Promise<void> {
  const role = pendingDelete.value;
  if (!role) return;
  const ok = await act(role, async () => {
    await adminClient.deleteRole(role.id);
    roles.value = roles.value.filter((r) => r.id !== role.id);
  });
  if (ok) closeDrawer();
  // On failure the dialog closes too; the error shows in the drawer.
  pendingDelete.value = null;
}

onMounted(() => { void load(); window.addEventListener("beforeunload", beforeUnload); });
onUnmounted(() => { window.removeEventListener("beforeunload", beforeUnload); answerDiscard(false); });
</script>

<template>
  <div class="roles-panel admin-panel">
    <section class="admin-panel-card" aria-labelledby="role-roster">
      <header class="admin-panel-head">
        <h2 id="role-roster">Role roster</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Role roster">A role is a named set of permissions. Open a role to change what it allows, and see which users hold it. Changes apply to every holder at once.</PanelHelp>
          <button v-if="auth.hasPermission('roles.manage')" type="button" class="admin-icon accent" data-test="new-role" aria-label="New role" title="New role" :disabled="loading || !!loadError" @click="openCreate"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button>
          <AdminSearch ref="searchField" v-model="search" label="Search roles" />
        </div>
      </header>
      <ActionMessage v-if="loadError" kind="error" :text="loadError" class="admin-panel-text"><button type="button" class="chip" @click="load">Retry</button></ActionMessage>
      <p v-else-if="loading" class="admin-panel-text muted" role="status">Loading roles…</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">{{ roles.length ? "No roles match your search." : "No roles yet. Create one to get started." }}
        <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button>
      </p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="role-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">Role</th><th scope="col" class="users-col">Users</th></tr></thead>
          <tbody>
            <tr v-for="r in visible" :key="r.id" :data-id="r.id" data-test="role" :class="{ selected: r.id === selectedId }">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="select(r)">{{ r.name }}</button><span v-if="r.is_protected" class="badge">protected</span>
                <p v-if="r.description" class="description">{{ r.description }}</p></th>
              <td class="users-col" :title="`${r.account_count} users`">{{ r.account_count > 999 ? "+999" : r.account_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!loading && !loadError && roles.length" class="admin-panel-text muted count" role="status">{{ visible.length }} of {{ roles.length }} roles</p>
    </section>

    <RecordDrawer ref="drawer" :open="selected !== null" :title="selected ? `Role ${selected.name}` : 'Role details'"
      :editable="canEdit" :editing="editing" :busy="busy" :fallback-focus="() => searchField?.focus()"
      @edit="editing = true; actionError = ''" @close="closeDrawer" @discard="discardEdit" @save="saveRole">
      <RoleEditor v-if="selected" ref="roleEditor" :role="selected" :permissions="permissions" :busy="busy" :error="actionError" :editing="editing"
        :saved="saved" :affected="affected" @dirty="dirty = $event; if ($event) saved = false" @show-accounts="showAccounts" @remove="pendingDelete = selected" />
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="busy" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="button" class="primary" :disabled="busy || !roleEditor?.dirty || !roleEditor?.valid" :aria-busy="busy" data-test="save-role" @click="requestSave('role-editor', drawer)">Save changes</button>
      </template>
    </RecordDrawer>

    <RecordDrawer ref="createDrawer" :open="creating" title="New role" :editing="true" :busy="newRole.saving" :fallback-focus="() => searchField?.focus()" save-label="Create role"
      @close="creating = false" @discard="creating = false" @save="createRole">
      <form id="role-create" class="create admin-editor" @submit.prevent>
        <label>Name<input v-model="newRole.name" type="text" maxlength="80" required :disabled="newRole.saving" /></label>
        <label>Description<input v-model="newRole.description" type="text" maxlength="255" placeholder="Optional" :disabled="newRole.saving" /></label>
        <ActionMessage v-if="newRole.error" kind="error" :text="newRole.error" />
      </form>
      <template #footer>
        <button type="button" class="chip" :disabled="newRole.saving" @click="creating = false">Cancel</button>
        <button type="button" class="primary" :disabled="newRole.saving || !newRole.name.trim()" :aria-busy="newRole.saving" data-test="create-role" @click="requestSave('role-create', createDrawer)">Create role</button>
      </template>
    </RecordDrawer>

    <ConfirmModal
      :open="pendingDelete !== null"
      title="Delete role"
      :message="deleteMessage"
      confirm-label="Delete"
      danger
      :require-text="pendingDelete && pendingDelete.account_count > 0 ? pendingDelete.name : ''"
      :busy="busy"
      @confirm="confirmDelete"
      @close="pendingDelete = null"
    />
    <ConfirmModal :open="discardOpen" title="Discard unsaved changes?" message="Your role changes have not been saved." confirm-label="Discard changes" @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </div>
</template>

<style scoped>
.roles-panel { min-width: 0; }
.description { margin: 2px 0 0; color: var(--muted); font-size: 0.8em; font-style: italic; font-weight: 400; }
.users-col { width: 5.5rem; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.badge { margin-inline-start: 6px; }
.admin-records tbody tr.selected { background: var(--surface); }
.create { max-width: none; }
.create label { display: grid; gap: 4px; font-size: 0.85em; }
.count { border-top: 1px solid var(--border); font-size: 0.8rem; }
</style>
