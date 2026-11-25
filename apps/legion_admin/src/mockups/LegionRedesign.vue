<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import type { AgentStatus } from "../api/AgentsAdminClient";
import { BaseModal } from "@citadel/ui";
import { ConfirmModal } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { SettingRow } from "@citadel/ui";
import { ToggleSwitch } from "@citadel/ui";
import type { Theme } from "@citadel/ui";
import { LEGION_PAGES } from "../router/pages";
import { ADMIN_APPS, adminAppUrl } from "@citadel/ui";
import PanelSearch from "./PanelSearch.vue";

interface Agent {
  id: string;
  name: string;
  role: string;
  status: AgentStatus;
  gateway: string;
  description: string;
}

interface Connection {
  name: string;
  description: string;
  url: string;
}

const agents = ref<Agent[]>([
  { id: "ember", name: "Ember", role: "Orchestrator", status: "running", gateway: "ConversationGateway", description: "Handles incoming conversations and delegates work to specialist agents." },
  { id: "router", name: "Router", role: "Internal router", status: "running", gateway: "DecisionGateway", description: "Selects a specialist agent and the right model tier for each request." },
  { id: "researcher", name: "Researcher", role: "Specialist", status: "running", gateway: "ConversationGateway", description: "Researches questions and summarizes findings with sources." },
  { id: "code-architect", name: "Code Architect", role: "Specialist", status: "running", gateway: "ConversationGateway", description: "Designs software changes and outlines implementation plans." },
  { id: "code-writer", name: "Code Writer", role: "Specialist", status: "offline", gateway: "ConversationGateway", description: "Implements software changes and writes focused tests." },
  { id: "reviewer", name: "Reviewer", role: "Specialist", status: "running", gateway: "ConversationGateway", description: "Reviews changes for correctness and regressions." },
  { id: "log-analyst", name: "Log Analyst", role: "Specialist", status: "disabled", gateway: "ConversationGateway", description: "Finds patterns and errors in application logs." },
]);

const connectionGroups = ref([
  {
    id: "model-gateways",
    title: "Model gateways",
    searchLabel: "Search model gateways",
    query: "",
    resources: [
      { name: "ConversationGateway", description: "Chat models", url: "https://conversation-gateway.example.invalid" },
      { name: "DecisionGateway", description: "Laya and Jev", url: "https://decision-gateway.example.invalid" },
    ],
  },
  {
    id: "mcp-servers",
    title: "MCP servers",
    searchLabel: "Search MCP servers",
    query: "",
    resources: [
      { name: "Armory", description: "Capability tools", url: "https://armory.example.invalid/mcp" },
    ],
  },
]);

const states = [
  { value: "all", label: "Configured" },
  { value: "running", label: "Running" },
  { value: "offline", label: "Offline" },
  { value: "disabled", label: "Disabled" },
] as const;
const statusText: Record<AgentStatus, string> = { running: "Running", offline: "Offline", disabled: "Disabled" };
const previewPages = LEGION_PAGES.filter(({ to }) => to !== "/servers");
const page = ref(previewPages[0]!);
const theme = ref<Theme>("dark");
const shortcutBase = location.protocol === "file:" ? "http://127.0.0.1/" : location.href;
const shortcuts = ADMIN_APPS.filter((app) => app.letter !== "L");
const sidebarExpanded = ref(window.matchMedia("(min-width: 768px)").matches);
const logoutRequested = ref(false);
const query = ref("");
const filter = ref<AgentStatus | "all">("all");
const selected = ref<Agent | null>(null);
const selectedConnection = ref<Connection | null>(null);
const connectionDraft = ref({ description: "", url: "" });
const editing = ref(false);
const confirmation = ref<"save" | "discard" | "close" | "limits" | null>(null);
const drawerTitle = computed(() => {
  if (selectedConnection.value) return editing.value ? "Edit connection" : "Connection details";
  return editing.value ? "Edit agent" : "Agent details";
});
const expanded = ref(false);
const pageView = ref<InstanceType<typeof PageLayout>>();
const editorField = ref<HTMLInputElement | HTMLTextAreaElement>();
const editButton = ref<HTMLButtonElement>();
const draftName = ref("");
const draftEnabled = ref(false);
const notice = ref("");
const limitQuery = ref("");
const limitSearch = ref<InstanceType<typeof PanelSearch>>();
const limits = ref([
  { id: "max_output_tokens", label: "Max output tokens", description: "Maximum generated tokens per response.", initial: 4096, min: 1, max: 200000 },
  { id: "max_context_tokens", label: "Max context tokens", description: "Maximum tokens available in the conversation context.", initial: 128000, min: 1000, max: 2000000 },
  { id: "max_tool_rounds", label: "Max tool rounds", description: "Maximum rounds of tool calls before the agent must answer.", initial: 12, min: 1, max: 100 },
].map((limit) => ({ ...limit, value: limit.initial, saved: limit.initial })));

const totals = computed(() => ({
  all: agents.value.length,
  running: agents.value.filter((agent) => agent.status === "running").length,
  offline: agents.value.filter((agent) => agent.status === "offline").length,
  disabled: agents.value.filter((agent) => agent.status === "disabled").length,
}));
const visibleAgents = computed(() => {
  const search = query.value.trim().toLowerCase();
  return agents.value.filter((agent) =>
    (filter.value === "all" || agent.status === filter.value) &&
    `${agent.name} ${agent.id} ${agent.role} ${agent.gateway}`.toLowerCase().includes(search),
  );
});
const visibleConnectionGroups = computed(() => connectionGroups.value.map((group) => {
  const search = group.query.trim().toLowerCase();
  const rows = group.resources.filter((resource) => `${resource.name} ${resource.description} ${resource.url}`.toLowerCase().includes(search));
  return { group, rows };
}));
const visibleLimitIds = computed(() => {
  const search = limitQuery.value.trim().toLowerCase();
  return new Set(limits.value.filter((limit) => `${limit.label} ${limit.description}`.toLowerCase().includes(search)).map((limit) => limit.id));
});
const limitsDirty = computed(() => limits.value.some((limit) => limit.value !== limit.saved));

async function saveLimits(): Promise<void> {
  if (!limitsDirty.value) return;
  for (const limit of limits.value) limit.saved = limit.value;
  notice.value = "Token limits saved in this preview.";
  await nextTick();
  limitSearch.value?.focus();
}

async function revealInvalidLimit(event: Event): Promise<void> {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || input.getClientRects().length) return;
  event.preventDefault();
  if (!limitQuery.value) return;
  limitQuery.value = "";
  await nextTick();
  input.reportValidity();
}

function navigate(destination: typeof page.value): void {
  page.value = destination;
  notice.value = "";
  pageView.value?.$el.scrollTo(0, 0);
}

function closeDrawer(): void {
  selected.value = null;
  selectedConnection.value = null;
  expanded.value = false;
  editing.value = false;
}

function requestDrawerClose(): void {
  if (editing.value) confirmation.value = "close";
  else closeDrawer();
}

function saveConnection(): void {
  const connection = selectedConnection.value;
  if (!connection) return;
  connection.description = connectionDraft.value.description.trim();
  connection.url = connectionDraft.value.url.trim();
  notice.value = `${connection.name} updated in this preview.`;
}

async function beginEdit(): Promise<void> {
  const connection = selectedConnection.value;
  const agent = selected.value;
  if (connection) {
    connectionDraft.value = { description: connection.description, url: connection.url };
  } else if (agent) {
    draftName.value = agent.name;
    draftEnabled.value = agent.status !== "disabled";
  }
  notice.value = "";
  editing.value = true;
  await nextTick();
  editorField.value?.focus();
}

async function showDetails(): Promise<void> {
  editing.value = false;
  await nextTick();
  editButton.value?.focus();
}

function saveAgent(): void {
  const agent = selected.value;
  const name = draftName.value.trim();
  if (!agent || !name) return;
  agent.name = name;
  if (!draftEnabled.value) agent.status = "disabled";
  else if (agent.status === "disabled") agent.status = "offline";
  notice.value = `${name} updated in this preview.`;
}

async function confirmEdit(): Promise<void> {
  const action = confirmation.value;
  confirmation.value = null;
  if (!action) return;
  await nextTick();
  if (action === "limits") {
    for (const limit of limits.value) limit.value = limit.saved;
    notice.value = "";
    await nextTick();
    limitSearch.value?.focus();
    return;
  }
  if (action === "close") {
    closeDrawer();
    return;
  }
  if (action === "save") {
    if (selectedConnection.value) saveConnection();
    else saveAgent();
  }
  await showDetails();
}
</script>

<template>
  <div class="redesign" :class="{ 'sidebar-collapsed': !sidebarExpanded }" :style="{ colorScheme: theme === 'system' ? 'light dark' : theme }">
    <header class="app-header">
      <button
        type="button"
        class="sidebar-toggle"
        aria-controls="preview-sidebar"
        :aria-expanded="sidebarExpanded"
        :aria-label="sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'"
        :title="sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar'"
        @click="sidebarExpanded = !sidebarExpanded"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M9 5v14" /></svg>
      </button>
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z M4 7.5l8 4.5 8-4.5 M12 12v9 M8 5.3l8 4.5" /></svg>
        </span>
        <span>Legion Admin</span>
      </div>
      <h1 class="current-page">{{ page.label }}</h1>
      <div class="header-tools">
        <button type="button" class="header-tool" aria-label="Notifications" title="Notifications" popovertarget="preview-notifications">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
        </button>
        <section id="preview-notifications" class="header-popover" popover aria-label="Notifications">
          <h2>Notifications</h2>
          <button v-if="totals.offline" type="button" class="popover-action" popovertarget="preview-notifications" popovertargetaction="hide" @click="navigate(LEGION_PAGES[0]!); query = ''; filter = 'offline'">
            {{ totals.offline }} offline {{ totals.offline === 1 ? 'agent' : 'agents' }}
          </button>
          <p v-else>No offline agents.</p>
        </section>
        <button type="button" class="header-tool" aria-label="Help" title="Help" popovertarget="preview-help">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9.1 9a3 3 0 1 1 4.8 2.4c-1.4 1-1.9 1.6-1.9 2.6M12 17h.01" /></svg>
        </button>
        <section id="preview-help" class="header-popover" popover aria-label="Help">
          <h2>About this preview</h2>
          <p>Uses sample data. Edits stay in this tab until you reload.</p>
        </section>
        <button type="button" class="header-tool profile" aria-label="Profile" title="Profile" popovertarget="preview-profile">PA</button>
        <section id="preview-profile" class="header-popover" popover aria-label="Profile">
          <h2>Preview account</h2>
          <div class="theme-field">
            <label for="preview-theme">Theme</label>
            <span class="theme-select">
              <select id="preview-theme" v-model="theme">
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="system">System</option>
              </select>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            </span>
          </div>
          <button type="button" class="popover-action" @click="logoutRequested = true">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg>
            <span>Log out</span>
          </button>
          <p v-if="logoutRequested" role="status">No account is signed in to this mockup.</p>
        </section>
      </div>
    </header>
    <aside id="preview-sidebar" class="rail">
      <nav aria-label="Admin sections">
        <button v-for="item in previewPages" :key="item.to" type="button" :aria-label="item.label" :title="sidebarExpanded ? undefined : item.label" :aria-current="page.to === item.to ? 'page' : undefined" @click="navigate(item)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path v-for="path in item.icon" :key="path" :d="path" /></svg>
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="rail-footer">
        <nav class="rail-shortcuts" aria-label="Other admin apps">
          <a v-for="app in shortcuts" :key="app.port" :href="adminAppUrl(app.port, shortcutBase)" :aria-label="app.name" :title="app.name">
            <b aria-hidden="true">{{ app.letter }}</b><span>{{ app.name }}</span>
          </a>
        </nav>
      </div>
    </aside>

    <main class="workspace">
      <PageLayout ref="pageView" :title="page.label" wide>
        <template v-if="page.to === '/agents'">
          <div class="overview" role="group" aria-label="Filter agents by status">
            <button v-for="state in states" :key="state.value" type="button" :aria-pressed="filter === state.value" @click="filter = state.value">
              <span :class="['state-dot', state.value]" aria-hidden="true" />{{ state.label }}
              <strong>{{ totals[state.value] }}</strong>
            </button>
          </div>

          <section class="panel roster" aria-labelledby="roster-title">
            <header class="panel-header">
              <h3 id="roster-title">Agent roster</h3>
              <div class="panel-tools"><PanelSearch v-model="query" label="Search agents" /></div>
            </header>

            <div v-if="visibleAgents.length" class="table-scroll" tabindex="0" role="region" aria-labelledby="roster-title">
              <table aria-labelledby="roster-title">
                <thead><tr><th scope="col">Agent</th><th scope="col">Role</th><th scope="col">State</th></tr></thead>
                <tbody>
                  <tr v-for="agent in visibleAgents" :key="agent.id" :class="{ selected: selected?.id === agent.id }">
                    <th scope="row">
                      <button class="record-link" type="button" aria-haspopup="dialog" aria-controls="record-drawer" @click="notice = ''; selected = agent">
                        <span class="initials" aria-hidden="true">{{ agent.name.slice(0, 2).toUpperCase() }}</span>
                        <span class="record-name"><strong>{{ agent.name }}</strong><code>{{ agent.id }}</code></span>
                      </button>
                    </th>
                    <td>{{ agent.role }}</td>
                    <td><span :class="['status', agent.status]"><span :class="['state-dot', agent.status]" aria-hidden="true" />{{ statusText[agent.status] }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty">
              <p>No agents match your search and filter.</p>
              <button type="button" class="secondary" @click="query = ''; filter = 'all'">Clear filters</button>
            </div>
            <p class="roster-footer" role="status">{{ visibleAgents.length }} of {{ totals.all }} agents</p>
          </section>
        </template>

        <section v-else-if="page.to === '/tuning'" class="panel settings" aria-labelledby="settings-title">
          <header class="panel-header">
            <h3 id="settings-title">Token limits</h3>
            <div class="panel-tools">
              <span class="edit-slot">
                <button v-if="limitsDirty" type="button" class="header-tool" aria-label="Cancel changes" title="Cancel changes" @click="confirmation = 'limits'">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
                </button>
                <button v-if="limitsDirty" type="submit" form="preview-limits" class="header-tool panel-save" aria-label="Save token limits" title="Save token limits">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h12l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM7 3v6h9V3M7 21v-8h10v8" /></svg>
                </button>
              </span>
              <PanelSearch ref="limitSearch" v-model="limitQuery" label="Search token limits" />
            </div>
          </header>
          <form id="preview-limits" class="settings-body" @submit.prevent="saveLimits" @invalid.capture="revealInvalidLimit">
            <SettingRow v-for="limit in limits" v-show="visibleLimitIds.has(limit.id)" :key="limit.id" :setting-id="limit.id" :label="limit.label" :description="limit.description" :modified="limit.value !== limit.initial" @reset="limit.value = limit.initial; notice = ''">
              <input v-model.number="limit.value" type="number" :min="limit.min" :max="limit.max" required :aria-label="limit.label" @input="notice = ''" />
            </SettingRow>
          </form>
          <p v-if="!visibleLimitIds.size" class="empty" role="status">No token limits match your search.</p>
        </section>

        <div v-else-if="page.to === '/connections'" class="connections">
          <section v-for="{ group, rows } in visibleConnectionGroups" :key="group.id" class="panel resources" :aria-labelledby="group.id">
            <header class="panel-header">
              <h3 :id="group.id">{{ group.title }}</h3>
              <div class="panel-tools"><PanelSearch v-model="group.query" :label="group.searchLabel" /></div>
            </header>
            <div v-if="rows.length" class="table-scroll" tabindex="0" role="region" :aria-labelledby="group.id">
              <table :aria-labelledby="group.id">
                <thead><tr><th scope="col">Name</th><th scope="col">Connection URL</th></tr></thead>
                <tbody>
                  <tr v-for="resource in rows" :key="resource.name" :class="{ selected: selectedConnection?.name === resource.name }">
                    <th scope="row">
                      <button class="record-link" type="button" aria-haspopup="dialog" aria-controls="record-drawer" @click="notice = ''; selectedConnection = resource">
                        <span class="initials" aria-hidden="true">{{ resource.name.slice(0, 2).toUpperCase() }}</span>
                        <span class="record-name"><strong>{{ resource.name }}</strong><span v-if="resource.description" class="connection-description">{{ resource.description }}</span></span>
                      </button>
                    </th>
                    <td><code>{{ resource.url }}</code></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="empty" role="status">No connections match your search.</p>
          </section>
        </div>
        <p v-if="notice && !selected && !selectedConnection" class="notice" role="status">{{ notice }}</p>
      </PageLayout>
    </main>

    <BaseModal id="record-drawer" class="record-drawer" :class="{ expanded }" :open="selected !== null || selectedConnection !== null" :title="drawerTitle" side @close="requestDrawerClose">
      <div v-if="selected || selectedConnection" class="drawer-body">
        <div class="drawer-tools">
          <button v-if="!editing" ref="editButton" type="button" class="drawer-icon" :aria-label="selectedConnection ? 'Edit connection' : 'Edit agent'" title="Edit" @click="beginEdit">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 4 4M4 20l4.5-1 11-11a2.8 2.8 0 0 0-4-4l-11 11L4 20Z" /></svg>
          </button>
          <button type="button" class="drawer-icon drawer-expand" :aria-label="expanded ? 'Shrink drawer' : 'Expand drawer'" :title="expanded ? 'Shrink drawer' : 'Expand drawer'" :aria-pressed="expanded" @click="expanded = !expanded">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path v-if="expanded" d="M4 9h5V4m11 5h-5V4M4 15h5v5m11-5h-5v5" />
              <path v-else d="M9 4H4v5m11-5h5v5M9 20H4v-5m11 5h5v-5" />
            </svg>
          </button>
        </div>
        <form v-if="selectedConnection && editing" id="record-edit-form" class="editor connection-editor" @submit.prevent="confirmation = 'save'">
          <h4>{{ selectedConnection.name }}</h4>
          <label for="connection-description">Description</label>
          <textarea id="connection-description" ref="editorField" v-model="connectionDraft.description" rows="3" maxlength="240" />
          <label for="connection-url">Connection URL</label>
          <input id="connection-url" v-model.trim="connectionDraft.url" type="url" required pattern="https?://.+" aria-describedby="connection-url-hint" spellcheck="false" />
          <p id="connection-url-hint" class="connection-description">Use a URL starting with http:// or https://.</p>
        </form>
        <form v-else-if="selected && editing" id="record-edit-form" class="editor" @submit.prevent="confirmation = 'save'">
          <label>Display name <input ref="editorField" v-model.trim="draftName" required pattern=".*\S.*" maxlength="60" /></label>
          <ToggleSwitch :checked="draftEnabled" :disabled="selected.id === 'ember'" @change="draftEnabled = ($event.target as HTMLInputElement).checked">Agent enabled</ToggleSwitch>
        </form>
        <div v-else-if="selectedConnection" class="detail">
          <div class="detail-identity">
            <span class="initials large" aria-hidden="true">{{ selectedConnection.name.slice(0, 2).toUpperCase() }}</span>
            <h4>{{ selectedConnection.name }}</h4>
          </div>
          <p v-if="selectedConnection.description" class="description">{{ selectedConnection.description }}</p>
          <dl><div><dt>Connection URL</dt><dd><code>{{ selectedConnection.url }}</code></dd></div></dl>
        </div>
        <div v-else-if="selected" class="detail">
          <div class="detail-identity">
            <span class="initials large" aria-hidden="true">{{ selected.name.slice(0, 2).toUpperCase() }}</span>
            <div><h4>{{ selected.name }}</h4><code>{{ selected.id }}</code></div>
          </div>
          <p class="description">{{ selected.description }}</p>
          <dl>
            <div><dt>State</dt><dd><span :class="['status', selected.status]"><span :class="['state-dot', selected.status]" aria-hidden="true" />{{ statusText[selected.status] }}</span></dd></div>
            <div><dt>Role</dt><dd>{{ selected.role }}</dd></div>
            <div><dt>Gateway</dt><dd>{{ selected.gateway }}</dd></div>
            <div v-if="selected.id === 'ember'"><dt>Entry point</dt><dd>Default agent</dd></div>
          </dl>
        </div>
        <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      </div>
      <footer v-if="editing" class="editor-actions">
        <button type="button" class="secondary" @click="confirmation = 'discard'">Cancel</button>
        <button type="submit" form="record-edit-form" class="primary">Save</button>
      </footer>
    </BaseModal>
    <ConfirmModal
      :open="confirmation !== null"
      :title="confirmation === 'save' ? 'Save changes?' : 'Discard changes?'"
      :message="confirmation === 'save' ? 'Apply these changes to the preview?' : 'Your unsaved edits will be lost.'"
      :confirm-label="confirmation === 'save' ? 'Save changes' : 'Discard changes'"
      :danger="confirmation !== 'save'"
      @confirm="confirmEdit"
      @close="confirmation = null"
    />
  </div>
</template>

<style scoped src="./legion-redesign.css"></style>
