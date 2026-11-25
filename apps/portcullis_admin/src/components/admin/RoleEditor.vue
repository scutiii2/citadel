<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, reactive, ref, watch } from "vue";
import type { AdminAccount, PermissionInfo, Role, RoleChanges } from "../../api/AdminClient";
import { useAuthStore } from "../../stores/auth";
import { ToggleSwitch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import "@citadel/ui/admin.css";

/** One role in the record drawer: name and description, the grouped permission switches, the
 * accounts that hold it, and delete. The draft (`RoleChanges`) lives here, so searching permissions
 * never loses an edit; the parent owns `editing`, runs the calls and asks for confirmation. */
const props = defineProps<{
  role: Role;
  permissions: PermissionInfo[];
  busy: boolean;
  error: string;
  editing: boolean;
  /** The last change went through. */
  saved?: boolean;
  affected: { loading: boolean; error: string; accounts: AdminAccount[] | null };
}>();
const emit = defineEmits<{ showAccounts: []; dirty: [value: boolean]; remove: [] }>();

const auth = useAuthStore();
const canManage = computed(() => auth.hasPermission("roles.manage") && props.role.permissions.every(auth.hasPermission));
const form = reactive({ name: "", description: "" });
const search = ref("");
const draftPermissions = ref<string[]>([]);
const canViewAccounts = computed(() => ["accounts.view", "accounts.manage", "accounts.delete", "roles.assign"].some(auth.hasPermission));

const changes = computed<RoleChanges>(() => {
  const result: RoleChanges = {};
  if (!props.role.is_protected && form.name.trim() !== props.role.name) result.name = form.name.trim();
  if (form.description.trim() !== (props.role.description ?? "")) result.description = form.description.trim();
  if ([...draftPermissions.value].sort().join("\n") !== [...props.role.permissions].sort().join("\n")) result.permissions = [...draftPermissions.value].sort();
  return result;
});
const dirty = computed(() => Object.keys(changes.value).length > 0);
const valid = computed(() => form.name.trim() !== "");

function revert(): void {
  form.name = props.role.name;
  form.description = props.role.description ?? "";
  draftPermissions.value = [...props.role.permissions];
}
watch(() => props.role, revert, { immediate: true });
watch(() => props.role.id, () => { search.value = ""; });
watch(dirty, (value) => emit("dirty", value));
defineExpose({ dirty, valid, changes, revert });

function toggle(name: string): void {
  if (!props.editing || props.busy || props.role.is_protected || !canManage.value || !auth.hasPermission(name)) return;
  draftPermissions.value = draftPermissions.value.includes(name)
    ? draftPermissions.value.filter((p) => p !== name) : [...draftPermissions.value, name];
}

const labels: Record<string, string> = {
  "chat.use": "Use chat", "chat.share": "Share chats publicly", "files.upload": "Upload files", "files.download": "Download files",
  "tools.view": "Browse tools", "tools.execute": "Run tools", "extensions.personal.manage": "Manage personal extensions",
  "accounts.view": "View accounts", "accounts.manage": "Manage accounts", "accounts.delete": "Delete accounts",
  "roles.view": "View roles", "roles.manage": "Manage roles & permissions", "roles.assign": "Assign roles", "invites.manage": "Manage invites",
  "settings.manage": "Manage workspace settings", "capabilities.manage": "Manage shared capabilities", "tool_services.manage": "Manage tool services",
  "usage.all.view": "View all account usage", "logs.view": "View activity logs", "logs.errors.view": "View error logs",
  "logs.chat.view": "View chat logs", "logs.chat.prompts.view": "View agent prompts in chat logs", "config.issues.view": "View configuration issues", "traffic.view": "View network traffic",
};
const groups = computed(() => {
  const definitions = [
    { label: "Chat & files", names: ["chat.use", "chat.share", "files.upload", "files.download"] },
    { label: "Tools & personal extensions", names: ["tools.view", "tools.execute", "extensions.personal.manage"] },
    { label: "Accounts & access", names: ["accounts.view", "accounts.manage", "accounts.delete", "roles.view", "roles.manage", "roles.assign", "invites.manage"] },
    { label: "Workspace & monitoring", names: ["settings.manage", "capabilities.manage", "tool_services.manage", "usage.all.view", "logs.view", "logs.errors.view", "logs.chat.view", "logs.chat.prompts.view", "config.issues.view", "traffic.view"] },
  ];
  const known = new Set(definitions.flatMap((g) => g.names));
  definitions.push({ label: "Other permissions", names: props.permissions.filter((p) => !known.has(p.name)).map((p) => p.name) });
  const query = search.value.trim().toLowerCase();
  return definitions.map((group) => {
    const all = props.permissions.filter((p) => group.names.includes(p.name));
    return {
      label: group.label,
      total: all.length,
      enabled: all.filter((p) => draftPermissions.value.includes(p.name)).length,
      permissions: all.filter((p) => `${labels[p.name] ?? ""} ${p.name} ${p.description ?? ""}`.toLowerCase().includes(query)),
    };
  }).filter((g) => g.permissions.length);
});
</script>

<template>
  <div class="role-body admin-panel" :aria-label="`Role ${role.name}`">
    <form v-if="editing" id="role-editor" class="row-form" @submit.prevent>
      <label>Name<input v-model="form.name" type="text" maxlength="80" required :disabled="busy || role.is_protected" /></label>
      <label>Description<input v-model="form.description" type="text" maxlength="255" :disabled="busy" /></label>
    </form>
    <header v-else class="summary">
      <p class="lede">{{ role.description || "No description." }}</p>
      <ul class="facts" aria-label="Role facts">
        <li>{{ role.account_count }} {{ role.account_count === 1 ? "user" : "users" }}</li>
        <li>{{ role.is_protected ? "All" : draftPermissions.length }} {{ role.is_protected || draftPermissions.length !== 1 ? "permissions" : "permission" }}</li>
        <li v-if="role.is_protected" class="protected"><span class="badge">protected</span><PanelHelp title="Protected role"><p>This role always holds every permission and can't be renamed or deleted.</p></PanelHelp></li>
      </ul>
    </header>
    <ActionMessage v-if="error" kind="error" :text="error" />
    <p v-if="role.is_protected && editing" class="muted note">This role always holds every permission and can't be renamed or deleted.</p>
    <p v-else-if="!role.is_protected && !canManage" class="muted note">Read-only. Editing requires role management access and every permission held by this role.</p>
    <p v-if="!role.is_protected && editing" class="impact">Changes apply to {{ role.account_count }} {{ role.account_count === 1 ? "user" : "users" }} when you save.</p>
    <p class="apply muted" role="status">
      <span v-if="editing">Changes are a draft until you save.</span>
      <span v-if="busy">Saving…</span>
      <ActionMessage v-if="saved && !error && !dirty" kind="ok" text="Saved" />
    </p>

    <label class="permission-search"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0" /></svg><input v-model="search" type="search" placeholder="Find a permission" aria-label="Find a permission" /></label>
    <section v-for="group in groups" :key="group.label" class="permission-group" :aria-label="group.label">
      <div class="group-head"><h4>{{ group.label }}</h4><span>{{ group.enabled }} of {{ group.total }} enabled</span></div>
      <ul class="permissions" :aria-busy="busy">
        <li v-for="p in group.permissions" :key="p.name">
          <ToggleSwitch small :checked="draftPermissions.includes(p.name)" :disabled="!editing || role.is_protected || busy || !canManage || !auth.hasPermission(p.name)" :aria-label="p.name" @change="toggle(p.name)" />
          <div>
            <strong class="permission-label">{{ labels[p.name] ?? p.name }}</strong>
            <code>{{ p.name }}</code>
            <div v-if="p.description" class="muted description">{{ p.description }}</div>
          </div>
        </li>
      </ul>
    </section>
    <p v-if="!groups.length" class="muted">No permissions match your search.</p>

    <section v-if="canViewAccounts" class="affected-section">
      <h4>Affected users</h4>
      <button v-if="!affected.accounts && !affected.loading" type="button" class="small" :disabled="busy" @click="emit('showAccounts')">View affected users</button>
      <p v-if="affected.loading" role="status" class="muted">Loading accounts…</p>
      <template v-else-if="affected.error"><ActionMessage kind="error" :text="affected.error" /><button type="button" class="small" @click="emit('showAccounts')">Retry</button></template>
      <template v-else-if="affected.accounts">
        <p class="muted">{{ affected.accounts.length }} {{ affected.accounts.length === 1 ? "user holds" : "users hold" }} this role.</p>
        <ul class="affected-accounts"><li v-for="account in affected.accounts" :key="account.id"><strong>{{ account.username }}</strong><span>{{ account.email }}</span><small>{{ account.is_active ? "Active" : "Disabled" }} · {{ account.email_verified ? "Verified" : "Unverified" }}</small></li></ul>
      </template>
    </section>

    <section v-if="!role.is_protected && canManage && !editing" class="danger-zone">
      <h4>Danger zone</h4>
      <p class="muted description">Users holding this role lose its permissions. This can't be undone.</p>
      <button type="button" class="small danger" :disabled="busy" @click="emit('remove')">Delete role</button>
    </section>
  </div>
</template>

<style scoped>
.role-body { min-width: 0; padding-top: 4px; }
.row-form { display: grid; gap: 10px; }
.row-form label { display: grid; gap: 4px; font-size: 0.85em; }
.summary { display: grid; gap: 10px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.lede { margin: 0; overflow-wrap: anywhere; }
.facts { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0; padding: 0; list-style: none; }
.facts li { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--surface); color: var(--muted); font-size: 0.8em; }
.facts li.protected { padding: 0 0 0 2px; border: 0; background: none; }
.description { margin: 2px 0 0; font-size: 0.85em; }
.note { margin: 8px 0 0; font-size: 0.85em; }
.apply { display: flex; align-items: center; gap: 8px; margin: 12px 0 0; font-size: 0.85em; }
.chip.saved { color: var(--success); border-color: var(--success); }
.impact { margin: 16px 0 0; padding: 12px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); font-size: 0.9em; }
.permissions { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.permissions li { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-top: 1px solid var(--border); }
.permissions li > div { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.permissions li > .toggle { order: 1; flex-shrink: 0; }
.permission-label { display: block; font-size: 0.9em; font-weight: 500; }
.permission-search { display: flex; align-items: center; gap: 10px; margin: 16px 0; padding: 9px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.permission-search:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.permission-search svg { width: 17px; height: 17px; color: var(--muted); flex-shrink: 0; }
.permission-search input { width: 100%; min-width: 0; border: none; outline: none; background: transparent; font: inherit; font-size: 0.85em; }
.permission-group { margin-top: 10px; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.group-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; background: var(--surface); }
.group-head h4 { margin: 0; font-size: 0.85em; }
.group-head span { color: var(--muted); font-size: 0.75em; white-space: nowrap; }
.permissions code { font-family: var(--mono); font-size: 0.9em; }
.affected-section { margin-top: 18px; }
.affected-accounts { list-style: none; padding: 0; margin: 0; }
.affected-accounts li { display: flex; flex-direction: column; padding: 12px 0; border-top: 1px solid var(--border); overflow-wrap: anywhere; }
.affected-accounts span, .affected-accounts small { color: var(--muted); }
</style>
