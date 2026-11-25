<script setup lang="ts">
import { computed, nextTick, reactive, ref } from "vue";
import { BaseModal } from "@citadel/ui";
import EmberLogo from "../components/EmberLogo.vue";
import { PageLayout } from "@citadel/ui";
import { SettingRow } from "@citadel/ui";
import { ToggleSwitch } from "@citadel/ui";
import { ConfirmModal } from "@citadel/ui";
import { ADMIN_APPS, adminAppUrl } from "@citadel/ui";
import { pages, panels, samples, sectionsByPath, type PreviewRecord } from "./previewData";

const icons = {
  sidebar: ["M3 5h18v14H3zM9 5v14"], bell: ["M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"],
  help: ["M22 12a10 10 0 1 0-20 0 10 10 0 0 0 20 0ZM9 9a3 3 0 1 1 3 3v2m0 3h.01"],
  search: ["M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0Zm-1.5 4.5L20 20"],
  edit: ["m4 16 11-11 4 4L8 20H4zm9-9 4 4"], expand: ["M3 9V3h6m6 0h6v6m0 6v6h-6m-6 0H3v-6"],
  shrink: ["M3 9h6V3m12 6h-6V3m0 18v-6h6M9 21v-6H3"],
  cancel: ["m6 6 12 12M18 6 6 18"], chevron: ["m6 9 6 6 6-6"],
  save: ["M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-8h8v8"], plus: ["M12 5v14M5 12h14"],
  arrow: ["M5 12h14m-6-6 6 6-6 6"], check: ["m5 12 4 4L19 6"],
};

const records = reactive(structuredClone(samples));
const page = ref(pages[1]!);
const section = computed(() => sectionsByPath[page.value.to]);
const panel = computed(() => section.value ? panels[section.value] : undefined);
const queries = reactive({ accounts: "", roles: "", invites: "", issues: "", settings: "" });
const currentQuery = computed({
  get: () => queries[section.value ?? "settings"],
  set: (value: string) => { queries[section.value ?? "settings"] = value; },
});
const rows = computed(() => section.value ? records[section.value] : []);
const accountFilter = ref("All accounts");
const accountFilters = computed(() => [
  { label: "All accounts", total: records.accounts.length },
  { label: "Active", total: records.accounts.filter((account) => account.status === "Active").length },
  { label: "Disabled", total: records.accounts.filter((account) => account.status === "Disabled").length },
]);
const matches = (text: string, query: string) => text.toLowerCase().includes(query.trim().toLowerCase());
const accountRoles = (ids: string[]) => records.roles.filter((role) => ids.includes(role.id));
const groupText = (row: PreviewRecord) => row.roleIds ? accountRoles(row.roleIds).map((role) => role.name).join(", ") || "No roles" : row.group;
const visibleRows = computed(() => rows.value.filter((row) => (
  (section.value !== "accounts" || accountFilter.value === "All accounts" || row.status === accountFilter.value)
  && matches([row.name, row.subtitle, groupText(row), row.status].join(" "), currentQuery.value)
)));

const sidebarExpanded = ref(!window.matchMedia("(max-width: 767px)").matches);
const theme = ref("dark");
const signedOut = ref(false);
const notice = ref("");
const settingsSaved = ref(false);
const settingsDraft = ref(false);
const settingDescription = "Ask before each tool run for all accounts. Typed commands are unaffected.";
const settingsDirty = computed(() => settingsDraft.value !== settingsSaved.value);
const shortcuts = ADMIN_APPS.filter((app) => app.name !== "Portcullis Admin");
const shortcutUrl = (port: number) => adminAppUrl(port, location.protocol === "file:" ? "http://127.0.0.1/" : location.href);

const selected = ref<PreviewRecord>();
const draft = ref<PreviewRecord>();
const creating = ref(false);
const expanded = ref(false);
const confirm = ref<"save" | "discard" | "settings" | "settingsDiscard" | "logout" | "revoke">();
const content = ref<HTMLElement>();
const drawerBody = ref<HTMLElement>();
const editButton = ref<HTMLButtonElement>();
let opener: HTMLElement | null = null;
const roleOptions = computed(() => records.roles.map((role) => role.name));
const canEdit = computed(() => selected.value && !selected.value.protected && (section.value === "accounts" || section.value === "roles"));
const drawerTitle = computed(() => creating.value ? "Invite member" : ({
  accounts: "Account details", roles: "Role details", invites: "Invite details", issues: "Configuration check",
})[section.value ?? "accounts"]);
const confirmCopy = {
  save: { title: "Save changes?", message: "This updates the sample record in this preview.", label: "Save changes" },
  discard: { title: "Discard changes?", message: "Your changes to this record will be lost.", label: "Discard changes" },
  settings: { title: "Save workspace settings?", message: "This updates tool approval for the preview workspace.", label: "Save settings" },
  settingsDiscard: { title: "Discard changes?", message: "Your changes to workspace settings will be lost.", label: "Discard changes" },
  logout: { title: "Log out of preview?", message: "You can reopen the preview without signing in.", label: "Log out" },
  revoke: { title: "Revoke invite?", message: "The sample invite will be removed from Open invites.", label: "Revoke invite" },
};
const activeConfirm = computed(() => confirm.value ? confirmCopy[confirm.value] : undefined);

function navigate(target: typeof page.value) {
  page.value = target;
  notice.value = "";
  if (window.matchMedia("(max-width: 767px)").matches) sidebarExpanded.value = false;
  content.value?.querySelector(".page")?.scrollTo(0, 0);
}

function openRecord(record: PreviewRecord, event: MouseEvent) {
  opener = event.currentTarget as HTMLElement;
  selected.value = record;
  expanded.value = false;
}

function newInvite(event: MouseEvent) {
  opener = event.currentTarget as HTMLElement;
  creating.value = true;
  expanded.value = false;
  draft.value = { id: "", name: "", subtitle: "Invited by admin", group: "Member", status: "Pending", note: "Awaiting acceptance.", tone: "warning" };
}

async function editRecord() {
  if (!selected.value) return;
  const record = selected.value;
  draft.value = record.roleIds ? { ...record, roleIds: [...record.roleIds] } : { ...record };
  await nextTick();
  drawerBody.value?.querySelector<HTMLElement>("input, select, textarea")?.focus();
}

async function closeDrawer() {
  selected.value = undefined;
  draft.value = undefined;
  creating.value = false;
  await nextTick();
  opener?.focus();
  if (!opener?.isConnected) content.value?.querySelector<HTMLInputElement>("input[type=search]")?.focus();
  opener = null;
}

function requestClose() {
  if (draft.value) confirm.value = "discard";
  else void closeDrawer();
}

function requestSave() {
  if (draft.value?.name.trim()) confirm.value = "save";
}

async function finishEditing() {
  draft.value = undefined;
  await nextTick();
  editButton.value?.focus();
}

async function confirmAction() {
  const action = confirm.value;
  confirm.value = undefined;
  if (action === "discard") {
    if (creating.value) void closeDrawer();
    else void finishEditing();
  } else if (action === "save" && draft.value) {
    if (creating.value && draft.value.group !== undefined) {
      records.invites.unshift({ ...draft.value, name: draft.value.name.trim(), id: String(Date.now()) });
      notice.value = "Sample invite created.";
      void closeDrawer();
    } else if (selected.value) {
      const previousName = selected.value.name;
      Object.assign(selected.value, draft.value, { name: draft.value.name.trim() });
      if (section.value === "roles") {
        for (const record of records.invites) {
          if (record.group === previousName) record.group = selected.value.name;
        }
      }
      void finishEditing();
      notice.value = "Sample record saved.";
    }
  } else if (action === "settings" || action === "settingsDiscard") {
    // Close the confirmation before removing the control that opened it.
    await nextTick();
    if (action === "settings") {
      settingsSaved.value = settingsDraft.value;
      notice.value = "Sample workspace settings saved.";
    } else {
      settingsDraft.value = settingsSaved.value;
      notice.value = "";
    }
    await nextTick();
    content.value?.querySelector<HTMLInputElement>("input[type=search]")?.focus();
  } else if (action === "revoke") {
    records.invites = records.invites.filter((invite) => invite.id !== selected.value?.id);
    notice.value = "Sample invite revoked.";
    void closeDrawer();
  } else if (action === "logout") {
    signedOut.value = true;
  }
}

const initials = (name: string) => name.includes(" ") ? name.split(" ").slice(0, 2).map((part) => part[0]).join("").toUpperCase() : name.slice(0, 2).toUpperCase();
</script>

<template>
  <div class="prototype" :class="{ collapsed: !sidebarExpanded }" :style="{ colorScheme: theme === 'system' ? 'light dark' : theme }">
    <header class="topbar">
      <button v-if="!signedOut" type="button" class="icon-button sidebar-toggle" :aria-label="sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'" :aria-expanded="sidebarExpanded" aria-controls="preview-sidebar" @click="sidebarExpanded = !sidebarExpanded">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.sidebar[0]" /></svg>
      </button>
      <div class="brand"><EmberLogo /><strong>Portcullis Admin</strong></div>
      <h1 v-if="!signedOut">{{ page.label }}</h1>
      <div v-if="!signedOut" class="top-tools">
        <button type="button" class="icon-button" aria-label="Notifications" title="Notifications" popovertarget="preview-notifications">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.bell[0]" /></svg>
        </button>
        <section id="preview-notifications" class="top-popover" popover aria-label="Notifications">
          <h2>Notifications</h2>
          <button type="button" popovertarget="preview-notifications" popovertargetaction="hide" @click="navigate(pages[5]!)">Review configuration warning</button>
        </section>
        <button type="button" class="icon-button" aria-label="Help" title="Help" popovertarget="preview-help">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.help[0]" /></svg>
        </button>
        <section id="preview-help" class="top-popover" popover aria-label="Help">
          <h2>About this preview</h2>
          <p>Explore with sample data. Changes reset when you reload.</p>
        </section>
        <button type="button" class="icon-button profile" aria-label="Profile" title="Profile" popovertarget="preview-profile">AD</button>
        <section id="preview-profile" class="top-popover" popover aria-label="Profile">
          <h2>admin</h2>
          <div class="theme-field">
            <label for="preview-theme">Theme</label>
            <span class="theme-select">
              <select id="preview-theme" v-model="theme">
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="system">System</option>
              </select>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.chevron[0]" /></svg>
            </span>
          </div>
          <button type="button" popovertarget="preview-profile" popovertargetaction="hide" @click="confirm = 'logout'">Log out</button>
        </section>
      </div>
    </header>

    <aside v-if="!signedOut" id="preview-sidebar" class="sidebar">
      <nav aria-label="Portcullis navigation">
        <button v-for="item in pages" :key="item.to" type="button" :aria-current="item.to === page.to ? 'page' : undefined" :aria-label="item.label" :title="item.label" @click="navigate(item)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path v-for="path in item.icon" :key="path" :d="path" /></svg>
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <nav class="shortcuts" aria-label="Admin shortcuts">
        <a v-for="app in shortcuts" :key="app.port" :href="shortcutUrl(app.port)" :aria-label="app.name" :title="app.name" target="_blank" rel="noopener">
          <b aria-hidden="true">{{ app.letter }}</b><span>{{ app.name }}</span>
        </a>
      </nav>
    </aside>

    <main ref="content" class="workspace">
      <PageLayout :title="page.label" wide>
        <section v-if="signedOut" class="panel signed-out">
          <h2>Signed out of preview</h2>
          <button type="button" class="primary" @click="signedOut = false">Return to preview</button>
        </section>
        <template v-else-if="page.to === '/overview'">
          <section class="panel" aria-labelledby="overview-title">
            <div class="panel-header"><h2 id="overview-title">Workspace access</h2></div>
            <div class="overview-list">
              <button v-for="item in pages.slice(1)" :key="item.to" type="button" @click="navigate(item)">
                <span class="initials"><svg viewBox="0 0 24 24" aria-hidden="true"><path v-for="path in item.icon" :key="path" :d="path" /></svg></span>
                <span><strong>{{ item.label }}</strong><small>{{ item.to === '/admin/settings' ? 'Tool approval and workspace defaults' : item.to === '/config-issues' ? '1 warning to review' : records[sectionsByPath[item.to]!].length + ' ' + panels[sectionsByPath[item.to]!].count }}</small></span>
                <svg class="overview-arrow" viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.arrow[0]" /></svg>
              </button>
            </div>
          </section>
        </template>
        <template v-else>
          <div v-if="section === 'accounts'" class="account-filters" role="group" aria-label="Filter by account status">
            <button v-for="filter in accountFilters" :key="filter.label" type="button" :aria-pressed="accountFilter === filter.label" @click="accountFilter = filter.label">
              <i class="dot" :class="{ positive: filter.label === 'Active', accent: filter.label === 'All accounts' }" aria-hidden="true"></i>{{ filter.label }} <strong>{{ filter.total }}</strong>
            </button>
          </div>
          <section class="panel" aria-labelledby="panel-title">
            <div class="panel-header">
              <h2 id="panel-title">{{ panel?.heading ?? "Workspace controls" }}</h2>
              <div class="panel-tools">
                <span v-if="!section" class="edit-slot">
                  <button v-if="settingsDirty" type="button" class="icon-button" title="Cancel changes" aria-label="Cancel changes" @click="confirm = 'settingsDiscard'">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.cancel[0]" /></svg>
                  </button>
                  <button v-if="settingsDirty" type="button" class="icon-button save" title="Save workspace settings" aria-label="Save workspace settings" @click="confirm = 'settings'">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.save[0]" /></svg>
                  </button>
                </span>
                <label class="search">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.search[0]" /></svg>
                  <input v-model="currentQuery" type="search" :aria-label="panel?.search ?? 'Search settings'" :placeholder="panel?.search ?? 'Search settings'" />
                </label>
                <button v-if="section === 'invites'" type="button" class="primary invite" @click="newInvite">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.plus[0]" /></svg> Invite member
                </button>
              </div>
            </div>
            <template v-if="panel">
              <div v-if="visibleRows.length" class="table-scroll" role="region" aria-labelledby="panel-title" tabindex="0">
                <table>
                  <thead><tr><th scope="col">{{ panel.name }}</th><th scope="col">{{ panel.group }}</th><th scope="col">Status</th></tr></thead>
                  <tbody>
                    <tr v-for="row in visibleRows" :key="row.id" :class="{ selected: row.id === selected?.id }">
                      <th scope="row">
                        <button type="button" class="record" :aria-label="'Open details for ' + row.name" @click="openRecord(row, $event)">
                          <span class="initials" aria-hidden="true">{{ initials(row.name) }}</span>
                          <span class="record-name"><strong>{{ row.name }}</strong><small>{{ row.subtitle }}</small></span>
                        </button>
                      </th>
                      <td class="record-group">{{ groupText(row) }}</td>
                      <td><span class="status" :class="row.tone"><i class="dot" aria-hidden="true"></i>{{ row.status }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="empty">{{ rows.length ? 'No matches. Try a different search or filter.' : 'No ' + panel.count + ' to show.' }}</p>
              <p class="panel-footer">{{ visibleRows.length }} of {{ rows.length }} {{ panel.count }}</p>
            </template>
            <div v-else class="settings-body">
              <SettingRow v-if="matches('Tool approval Require approval for every tool ' + settingDescription, currentQuery)" setting-id="tool-approval" label="Require approval for every tool" :description="settingDescription" :modified="settingsDraft" @reset="settingsDraft = false">
                <ToggleSwitch aria-label="Require approval for every tool" :checked="settingsDraft" @change="settingsDraft = ($event.target as HTMLInputElement).checked" />
              </SettingRow>
              <p v-else class="empty">No settings match your search.</p>
            </div>
          </section>
          <p v-if="notice" class="notice" role="status"><svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.check[0]" /></svg>{{ notice }}</p>
        </template>
      </PageLayout>
    </main>

    <BaseModal :open="Boolean(selected || creating)" :title="drawerTitle" side class="record-drawer" :class="{ expanded }" @close="requestClose">
      <div class="drawer-tools">
        <button v-if="canEdit && !draft" ref="editButton" type="button" class="icon-button" aria-label="Edit record" title="Edit record" @click="editRecord">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons.edit[0]" /></svg>
        </button>
        <button type="button" class="icon-button" :aria-label="expanded ? 'Restore drawer width' : 'Expand drawer'" :title="expanded ? 'Restore drawer width' : 'Expand drawer'" @click="expanded = !expanded">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="expanded ? icons.shrink[0] : icons.expand[0]" /></svg>
        </button>
      </div>
      <div ref="drawerBody" class="drawer-body">
        <form v-if="draft" id="preview-record-editor" class="editor" @submit.prevent="requestSave">
          <label v-if="creating">Email address <input v-model="draft.name" type="email" required autocomplete="off" /></label>
          <label v-else-if="section === 'roles'">Role name <input v-model="draft.name" required /></label>
          <label v-if="creating">Role <select v-model="draft.group" aria-label="Role"><option v-for="role in roleOptions" :key="role">{{ role }}</option></select></label>
          <fieldset v-if="draft.roleIds" class="role-picker">
            <legend>Roles</legend>
            <label v-for="role in records.roles" :key="role.id">
              <input v-model="draft.roleIds" type="checkbox" :value="role.id" />
              {{ role.name }}
            </label>
          </fieldset>
          <label v-if="section === 'accounts'">Status <select v-model="draft.status" aria-label="Status" @change="draft.tone = draft.status === 'Active' ? 'positive' : 'neutral'"><option>Active</option><option>Disabled</option></select></label>
          <label v-if="section === 'roles'">Description <textarea v-model="draft.note" rows="4"></textarea></label>
        </form>
        <section v-else-if="selected" class="details">
          <div class="identity">
            <span class="initials large" aria-hidden="true">{{ initials(selected.name) }}</span>
            <div><h2>{{ selected.name }}</h2><p>{{ selected.subtitle }}</p></div>
          </div>
          <dl>
            <div>
              <dt>{{ panel?.group }}</dt>
              <dd>
                <ul v-if="selected.roleIds?.length" class="role-list" role="list">
                  <li v-for="role in accountRoles(selected.roleIds)" :key="role.id">{{ role.name }}</li>
                </ul>
                <template v-else>{{ groupText(selected) }}</template>
              </dd>
            </div>
            <div><dt>Status</dt><dd><span class="status" :class="selected.tone"><i class="dot" aria-hidden="true"></i>{{ selected.status }}</span></dd></div>
          </dl>
          <p v-if="selected.note" class="record-note">{{ selected.note }}</p>
          <button v-if="section === 'invites'" type="button" class="secondary danger" @click="confirm = 'revoke'">Revoke invite</button>
        </section>
      </div>
      <footer v-if="draft" class="drawer-footer">
        <button type="button" class="secondary" @click="requestClose">Cancel</button>
        <button type="submit" form="preview-record-editor" class="primary">{{ creating ? "Create invite" : "Save changes" }}</button>
      </footer>
    </BaseModal>
    <ConfirmModal :open="Boolean(activeConfirm)" :title="activeConfirm?.title ?? ''" :message="activeConfirm?.message ?? ''" :confirm-label="activeConfirm?.label" :danger="confirm === 'revoke'" @confirm="confirmAction" @close="confirm = undefined" />
  </div>
</template>

<style scoped src="./portcullis-redesign.css"></style>
