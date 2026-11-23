<script setup lang="ts">
import { computed } from "vue";
import type { AdminAccount, Role, RoleRef } from "../../api/AdminClient";
import { useAuthStore } from "../../stores/auth";
import { formatUtc } from "../../utils/errors";
import ToggleSwitch from "../ToggleSwitch.vue";
import "./admin.css";

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
  const known = new Map<number, RoleRef & { delegable: boolean }>();
  for (const role of props.roles) known.set(role.id, { id: role.id, name: role.name, delegable: role.permissions.every(auth.hasPermission) });
  for (const role of props.account.roles) if (!known.has(role.id)) known.set(role.id, { ...role, delegable: false });
  return [...known.values()].sort((a, b) => a.name.localeCompare(b.name));
});
const held = computed(() => new Set(props.account.roles.map((role) => role.id)));
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
  <div class="account-body admin-panel" :aria-label="`Account ${account.username}`">
    <div class="identity">
      <span class="avatar" aria-hidden="true">{{ account.username.slice(0, 2).toUpperCase() }}</span>
      <div class="who">
        <b class="name">{{ account.username }}</b>
        <span v-if="isSelf" class="self-label">Your account</span>
      </div>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <p v-if="locked" class="muted small-text">This is the protected admin account. It can't be edited, disabled or deleted.</p>

    <form v-if="editing" id="account-editor" class="edit" @submit.prevent>
      <template v-if="canManage">
        <label>Username<input :value="draft.username" type="text" required :disabled="busy" @input="patch({ username: ($event.target as HTMLInputElement).value })" /></label>
        <label>Email<input :value="draft.email" type="email" required :disabled="busy" @input="patch({ email: ($event.target as HTMLInputElement).value })" /></label>
      </template>
      <fieldset v-if="canAssign || account.roles.length" class="roles-edit">
        <legend>Roles</legend>
        <label v-for="role in choices" :key="role.id" class="role-choice">
          <input type="checkbox" :checked="draft.roleIds.includes(role.id)" :disabled="disabledChoice(role)" @change="toggleRole(role.id, ($event.target as HTMLInputElement).checked)" />
          {{ role.name }}
        </label>
        <p v-if="!choices.length" class="muted">No roles</p>
      </fieldset>
    </form>
    <template v-else>
      <div class="profile-meta">
        <p class="account-email">{{ account.email }}</p>
        <p class="joined"><span>Joined</span><time>{{ formatUtc(account.created_at) }}</time></p>
      </div>
      <section class="roles-section">
        <h4>Roles</h4>
        <div class="chips">
          <span v-for="r in account.roles" :key="r.id" class="chip fixed">{{ r.name }}</span>
          <span v-if="account.roles.length === 0" class="muted">No roles</span>
        </div>
      </section>
    </template>

    <section v-if="canDisable" class="active-section">
      <ToggleSwitch small :checked="account.is_active" :disabled="busy || editing" @change="requestActive($event)">Active</ToggleSwitch>
    </section>

    <div v-if="!locked && !account.email_verified && canManage" class="buttons">
      <button type="button" class="small" :disabled="busy || editing" @click="emit('sendVerification')">Send verification</button>
    </div>

    <section v-if="!locked && !isSelf && auth.hasPermission('accounts.delete')" class="danger-zone">
      <h4>Danger zone</h4>
      <p class="muted small-text">Removes the account for good. This can't be undone.</p>
      <button type="button" class="small danger" :disabled="busy || editing" @click="emit('remove')">Delete account</button>
    </section>
  </div>
</template>

<style scoped>
.account-body { display: flex; flex-direction: column; gap: 0; }
.identity { display: flex; align-items: center; gap: 12px; min-width: 0; padding-top: 4px; }
.avatar { width: 44px; height: 44px; flex-shrink: 0; display: grid; place-items: center; border-radius: var(--radius-full); color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--surface)); font-size: 0.85em; font-weight: 600; }
.who { display: flex; flex-direction: column; min-width: 0; }
.name { font-size: 1.05em; font-weight: 600; overflow-wrap: anywhere; }
.self-label { color: var(--muted); font-size: 0.75em; margin-top: 2px; }
.profile-meta { margin-top: 14px; }
.account-email { margin: 0; font-size: 0.85em; overflow-wrap: anywhere; }
.joined { display: flex; flex-direction: column; gap: 2px; margin: 10px 0 0; color: var(--muted); font-size: 0.75em; }
.account-body > .error, .account-body > .notice, .account-body > .small-text { margin: 14px 0 0; }
.small-text { font-size: 0.85em; }
h4 { margin: 0 0 12px; font-size: 0.85em; font-weight: 600; }
.account-body > section { margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--border); }
.edit { display: grid; gap: 12px; margin-top: 18px; }
.edit > label { display: grid; gap: 4px; font-size: 0.85em; }
.edit input[type="text"], .edit input[type="email"] { min-height: 40px; }
.roles-edit { display: grid; gap: 6px; margin: 0; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.roles-edit legend { padding: 0 6px; font-size: 0.85em; font-weight: 600; }
.role-choice { display: flex; align-items: center; gap: 8px; min-height: 36px; font-size: 0.9em; overflow-wrap: anywhere; }
.buttons { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 20px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
