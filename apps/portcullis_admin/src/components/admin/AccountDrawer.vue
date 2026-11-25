<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, ref } from "vue";
import type { AdminAccount, Role, RoleRef } from "../../api/AdminClient";
import { useAuthStore } from "../../stores/auth";
import { formatUtc } from "../../utils/errors";
import { ToggleSwitch } from "@citadel/ui";
import "@citadel/ui/admin.css";

/** The body of the account drawer: every assigned role (or "No roles"), and while editing the
 * staged profile fields and role choices, kept by role ID. It only reports what the admin chose:
 * the panel owns the draft, runs the calls and asks for confirmation. */
export interface AccountDraft { username: string; email: string; roleIds: number[] }

const props = defineProps<{
  account: AdminAccount;
  roles: Role[];
  isSelf: boolean;
  busy: boolean;
  error: string;
  notice: string;
  editing: boolean;
  draft: AccountDraft;
}>();

const emit = defineEmits<{
  "update:draft": [draft: AccountDraft];
  setActive: [active: boolean];
  sendVerification: [];
  remove: [];
}>();

const auth = useAuthStore();
const canManage = computed(() => auth.hasPermission("accounts.manage"));
const canAssign = computed(() => auth.hasPermission("roles.assign"));
/** Protected accounts can't be changed at all; your own can't be disabled or deleted. */
const locked = computed(() => props.account.is_protected);
const canDisable = computed(() => canManage.value && !locked.value && !props.isSelf);

/** Every role the editor can show: the known roles plus any the account holds that the list lacks. */
const choices = computed(() => {
  const known = new Map<number, RoleRef & { delegable: boolean; description: string }>();
  for (const role of props.roles) known.set(role.id, { id: role.id, name: role.name, description: role.description ?? "", delegable: role.permissions.every(auth.hasPermission) });
  for (const role of props.account.roles) if (!known.has(role.id)) known.set(role.id, { ...role, description: "", delegable: false });
  return [...known.values()].sort((a, b) => a.name.localeCompare(b.name));
});
const held = computed(() => new Set(props.account.roles.map((role) => role.id)));
const roleQuery = ref("");
const matchesRole = (role: { name: string; description: string }) => {
  const query = roleQuery.value.trim().toLowerCase();
  return !query || `${role.name} ${role.description}`.toLowerCase().includes(query);
};
/** The roles shown for the current search: every choice while editing, only the held ones otherwise. */
const shownRoles = computed(() => choices.value.filter((role) => (props.editing || held.value.has(role.id)) && matchesRole(role)));
const chosenCount = computed(() => (props.editing ? props.draft.roleIds.length : props.account.roles.length));
const status = computed(() => (!props.account.is_active ? "disabled" : !props.account.email_verified ? "unverified" : "active"));
/** A role can be newly granted only when its permissions are all held by the actor; any held role can be removed. */
const disabledChoice = (role: { id: number; delegable: boolean }) => props.busy || !canAssign.value || (!held.value.has(role.id) && !role.delegable);

function patch(change: Partial<AccountDraft>): void {
  emit("update:draft", { ...props.draft, ...change });
}

function toggleRole(id: number, checked: boolean): void {
  const ids = new Set(props.draft.roleIds);
  if (checked) ids.add(id);
  else ids.delete(id);
  patch({ roleIds: [...ids] });
}

function requestActive(event: Event): void {
  const input = event.target as HTMLInputElement;
  const wanted = input.checked;
  input.checked = props.account.is_active;
  emit("setActive", wanted);
}
</script>

<template>
  <div class="account-body admin-panel" :aria-label="`User ${account.username}`">
    <div class="identity">
      <span class="avatar" aria-hidden="true">{{ account.username.slice(0, 2).toUpperCase() }}</span>
      <div class="who">
        <b class="name">{{ account.username }}</b>
        <span class="account-email">{{ account.email }}</span>
      </div>
      <span class="status-pill" :class="status">{{ status }}</span>
    </div>
    <ul class="facts" aria-label="User facts">
      <li>Joined <time>{{ formatUtc(account.created_at) }}</time></li>
      <li v-if="isSelf">Your account</li>
      <li v-if="locked">Protected</li>
    </ul>

    <ActionMessage v-if="error" kind="error" :text="error" />
    <ActionMessage v-if="notice" kind="ok" :text="notice" />
    <p v-if="locked" class="muted small-text">The protected admin user can't be edited, disabled or deleted.</p>

    <form v-if="editing && canManage" id="account-editor" class="edit" @submit.prevent>
      <label>Username<input :value="draft.username" type="text" required :disabled="busy" @input="patch({ username: ($event.target as HTMLInputElement).value })" /></label>
      <label>Email<input :value="draft.email" type="email" required :disabled="busy" @input="patch({ email: ($event.target as HTMLInputElement).value })" /></label>
    </form>
    <form v-else-if="editing" id="account-editor" @submit.prevent></form>

    <section v-if="!editing || canAssign || account.roles.length" class="roles-section" aria-label="Roles">
      <div class="roles-head"><h4>Roles</h4><span class="count">{{ chosenCount }} of {{ choices.length }}{{ editing ? " selected" : "" }}</span></div>
      <label v-if="choices.length > 4" class="role-search"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0" /></svg><input v-model="roleQuery" type="search" placeholder="Find a role" aria-label="Find a role" /></label>
      <ul v-if="shownRoles.length" class="role-list">
        <li v-for="role in shownRoles" :key="role.id" class="role-row">
          <div v-if="editing" class="role-choice">
            <ToggleSwitch small :checked="draft.roleIds.includes(role.id)" :disabled="disabledChoice(role)" @change="toggleRole(role.id, ($event.target as HTMLInputElement).checked)">{{ role.name }}</ToggleSwitch>
          </div>
          <strong v-else class="role-name">{{ role.name }}</strong>
          <p v-if="role.description" class="role-desc">{{ role.description }}</p>
        </li>
      </ul>
      <p v-else class="muted small-text">{{ roleQuery ? "No roles match your search." : "No roles" }}</p>
    </section>

    <section class="active-section" aria-label="Sign-in access">
      <h4>Sign-in access</h4>
      <template v-if="canDisable">
        <ToggleSwitch small :checked="account.is_active" :disabled="busy || editing" @change="requestActive($event)">{{ account.is_active ? "Active" : "Disabled" }}</ToggleSwitch>
        <p class="muted small-text">{{ account.is_active ? "Turn off to log this user out and stop them signing in." : "This user cannot sign in. Turn on to let them back in." }}</p>
      </template>
      <p v-else class="muted small-text">{{ locked ? "The protected admin user can't be disabled." : isSelf ? "You can't disable your own user." : "Disabling a user needs the accounts.manage permission." }} Currently {{ account.is_active ? "active" : "disabled" }}.</p>
    </section>

    <div v-if="!locked && !account.email_verified && canManage" class="buttons">
      <button type="button" class="small" :disabled="busy || editing" @click="emit('sendVerification')">Send verification</button>
    </div>

    <section v-if="!locked && !isSelf && auth.hasPermission('accounts.delete')" class="danger-zone">
      <h4>Danger zone</h4>
      <p class="muted small-text">Removes the user for good. This can't be undone.</p>
      <button type="button" class="small danger" :disabled="busy || editing" @click="emit('remove')">Delete user</button>
    </section>
  </div>
</template>

<style scoped>
.account-body { display: flex; flex-direction: column; gap: 0; }
.identity { display: flex; align-items: center; gap: 14px; min-width: 0; padding-top: 4px; }
.avatar { width: 52px; height: 52px; flex-shrink: 0; display: grid; place-items: center; border-radius: var(--radius-full); color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--surface)); font-size: 1em; font-weight: 600; }
.who { display: flex; flex: 1; flex-direction: column; gap: 2px; min-width: 0; }
.name { font-size: 1.15em; font-weight: 600; overflow-wrap: anywhere; }
.account-email { color: var(--muted); font-size: 0.85em; overflow-wrap: anywhere; }
.status-pill { flex-shrink: 0; padding: 2px 10px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.78em; text-transform: capitalize; color: var(--muted); }
.status-pill.active { color: var(--success); background: color-mix(in srgb, var(--success) 8%, var(--bg)); }
.status-pill.unverified { color: var(--warning); background: color-mix(in srgb, var(--warning) 8%, var(--bg)); }
.facts { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 12px 0 0; padding: 0; list-style: none; color: var(--muted); font-size: 0.78em; }
.account-body > .error, .account-body > .notice, .account-body > .small-text { margin: 14px 0 0; }
.small-text { font-size: 0.85em; }
h4 { margin: 0; font-size: 0.85em; font-weight: 600; }
.active-section h4 { margin-bottom: 10px; }
.account-body > section { margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--border); }
.edit { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 18px; }
.edit > label { display: grid; gap: 4px; font-size: 0.85em; }
.edit input[type="text"], .edit input[type="email"] { min-height: 40px; }
.roles-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.count { color: var(--muted); font-size: 0.78em; }
.role-search { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding: 7px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); }
.role-search:focus-within { border-color: var(--accent); }
.role-search svg { width: 15px; height: 15px; flex-shrink: 0; fill: none; stroke: var(--muted); stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.role-search input { width: 100%; min-width: 0; padding: 0; border: none; outline: none; background: transparent; font: inherit; font-size: 0.85em; }
.role-list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--border); border-radius: var(--radius-lg); max-height: 46dvh; overflow-y: auto; scrollbar-gutter: stable; }
.role-row { display: grid; gap: 2px; padding: 10px 14px; }
.role-row + .role-row { border-top: 1px solid var(--border); }
.role-choice { display: flex; align-items: center; gap: 8px; min-height: 32px; font-size: 0.9em; overflow-wrap: anywhere; }
.role-name { font-size: 0.9em; font-weight: 600; }
.role-desc { margin: 0; color: var(--muted); font-size: 0.78em; overflow-wrap: anywhere; }
.buttons { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 20px; }
</style>
