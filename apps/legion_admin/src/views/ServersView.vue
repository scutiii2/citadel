<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref, watch } from "vue";
import { agentsAdminClient, type McpServer } from "../api/AgentsAdminClient";
import { ConfirmModal } from "@citadel/ui";
import { AdminSearch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { RecordDrawer } from "@citadel/ui";
import FormTabs from "../components/admin/FormTabs.vue";
import ConnectionTestCells from "../components/ConnectionTestCells.vue";
import { PasswordInput } from "@citadel/ui";
import { errorMessage } from "../utils/errors";

/** The MCP servers Legion's agents use as tools. Saved in Legion's database; a change applies at Legion's next start.
 * The header value of a server is write-only: the server only says whether one is saved. */
const servers = ref<Record<string, McpServer>>({});
const loading = ref(true);
const loaded = ref(false);
const error = ref("");
const notice = ref("");
const saving = ref(false);
const loadError = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const panelTitle = ref<HTMLElement>();
const selected = ref<string | null>(null);
const selectedServer = computed(() => selected.value ? servers.value[selected.value] : undefined);
defineExpose({ focusPanel: () => panelTitle.value?.focus() });

const tab = ref("general");
const tabItems = [{ id: "general", label: "General" }, { id: "connection", label: "Connection" }];
const editing = ref<string | null>(null); // the id being edited; "" while adding
const id = ref("");
const label = ref("");
const description = ref("");
const transport = ref<"http" | "stdio">("http");
const url = ref("");

type AddressRow = {
  key: number;
  address: string;
  revision: number;
  unresolvedId?: string;
  name: string;
  found: boolean | null;
  overrideSet: boolean;
  token: string;
};

let nextAddressKey = 0;
function newAddress(): AddressRow {
  return { key: nextAddressKey++, revision: 0, address: "", name: "", found: null, overrideSet: false, token: "" };
}

const mode = ref<"catalog" | "direct">("catalog");
const addressRows = ref<AddressRow[]>([newAddress()]);

const command = ref("");
const args = ref("");
const headerName = ref("");
const headerValue = ref("");
const hadHeader = ref(false);
const removing = ref<string | null>(null);

function endpoint(server: McpServer) {
  if (server.transport === "stdio") return [server.command, ...(server.args ?? [])].filter(Boolean).join(" ");
  if (server.origins?.length) return server.origins.map((origin) => origin.origin
    ? origin.origin + (server.path ?? "/mcp") : `Unavailable catalog address (${origin.origin_id})`).join(", ");
  return server.url ?? "";
}

const rows = computed(() => {
  const query = search.value.trim().toLowerCase();
  return Object.entries(servers.value).filter(([key, server]) =>
    [key, server.label, server.description, endpoint(server)].some((value) => value?.toLowerCase().includes(query)))
    .sort(([a], [b]) => a.localeCompare(b));
});
const isNew = computed(() => editing.value === "");
const overrideNeedsConnectionToken = computed(() =>
  transport.value === "http" && mode.value === "catalog" &&
  addressRows.value.some((row) => row.token || row.overrideSet) &&
  !(headerName.value.trim() && (headerValue.value || hadHeader.value)),
);
const valid = computed(
  () =>
    /^[a-z0-9][a-z0-9_-]{0,62}$/.test(id.value) &&
    label.value.trim() !== "" &&
    !overrideNeedsConnectionToken.value &&
    (transport.value === "stdio"
      ? command.value.trim() !== ""
      : mode.value === "direct"
        ? url.value.trim() !== ""
        : addressRows.value.length > 0 &&
          addressRows.value.every((row) => row.address.trim() !== "" && (row.found === true || (row.found === false && row.name.trim() !== "")))),
);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    servers.value = await agentsAdminClient.servers();
    loaded.value = true;
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function open(serverId: string) {
  const server = serverId ? servers.value[serverId] : undefined;
  selected.value = serverId;
  editing.value = serverId;
  id.value = serverId;
  label.value = server?.label ?? "";
  description.value = server?.description ?? "";
  transport.value = server?.transport ?? "http";
  url.value = server?.url ?? "";
  const path = server?.path ?? "/mcp";
  if (server?.origins?.length) {
    mode.value = "catalog";
    addressRows.value = server.origins.map((o) => ({ ...newAddress(), address: o.origin ? o.origin + path : "", found: o.origin ? true : null, overrideSet: !!o.has_override, unresolvedId: o.origin ? undefined : o.origin_id }));
  } else {
    mode.value = server?.url ? "direct" : "catalog";
    addressRows.value = [newAddress()];
  }
  command.value = server?.command ?? "";
  args.value = (server?.args ?? []).join(" ");
  headerName.value = server?.auth?.type === "header" ? (server.auth.header_name ?? "") : "";
  hadHeader.value = server?.auth?.type === "header" && !!server.auth.has_value;
  headerValue.value = "";
  error.value = notice.value = "";
}

function addressChanged(row: AddressRow) {
  row.revision++;
  row.found = null;
  row.name = "";
  row.overrideSet = false;
  row.token = "";
  error.value = "";
}

async function check(row: AddressRow) {
  const address = row.address.trim();
  if (!address || row.found !== null) return;
  const revision = ++row.revision;
  const current = () => addressRows.value.includes(row) && row.revision === revision && editing.value !== null;
  try {
    const result = await agentsAdminClient.lookupOrigin(address);
    if (!current()) return;
    row.found = result.found;
    row.unresolvedId = undefined;
    if (result.found && result.group) row.name = result.group.name;
  } catch (err) {
    if (current()) {
      error.value = errorMessage(err);
    }
  }
}

function addAddress() { addressRows.value.push(newAddress()); }
function removeAddress(index: number) {
  addressRows.value.splice(index, 1);
  if (!addressRows.value.length) addAddress();
}

function discard() {
  editing.value = null;
  headerValue.value = "";
  addressRows.value = [];
  if (selected.value === "") selected.value = null;
}

function close() {
  discard();
  selected.value = null;
}

function submit() {
  if (saving.value || !valid.value) return;
  error.value = "";
  if (transport.value === "http") {
    const addresses = mode.value === "direct" ? [url.value] : addressRows.value.map((row) => row.address);
    const validUrls = addresses.every((address) => {
      try {
        return ["https:", "http:"].includes(new URL(address.trim()).protocol);
      } catch {
        return false;
      }
    });
    if (!validUrls) {
      error.value = "Enter an HTTP(S) URL for each connection address.";
      return;
    }
  }
  drawer.value?.requestSave();
}

/** An untouched header value is left out, so the stored one stays. */
function entry(): McpServer {
  const body: McpServer = { label: label.value.trim(), description: description.value.trim(), transport: transport.value };
  if (transport.value === "http" && mode.value === "direct") body.url = url.value.trim();
  else if (transport.value === "http") {
    body.addresses = addressRows.value.map((row) => ({
      address: row.address.trim(),
      ...(row.found ? {} : { name: row.name.trim() }),
      ...(row.token ? { header_value: row.token } : {}),
    }));
  }
  else {
    body.command = command.value.trim();
    body.args = args.value.split(/\s+/).filter(Boolean);
  }
  const old = editing.value ? servers.value[editing.value]?.auth : undefined;
  if (headerName.value.trim()) {
    body.auth = { type: "header", header_name: headerName.value.trim() };
    if (headerValue.value) body.auth.header_value = headerValue.value;
  } else if (old && old.type !== "header") {
    body.auth = { type: old.type, env_var: old.env_var };
  }
  return body;
}

async function save() {
  if (saving.value || !valid.value) return;
  saving.value = true;
  error.value = notice.value = "";
  try {
    await agentsAdminClient.saveServer(id.value, entry());
    await load();
    notice.value = "Saved. Legion uses the change at its next start.";
    if (servers.value[id.value]) {
      selected.value = id.value;
      discard();
    } else {
      close();
    }
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!removing.value) return;
  saving.value = true;
  error.value = notice.value = "";
  try {
    await agentsAdminClient.removeServer(removing.value);
    delete servers.value[removing.value];
    close();
    notice.value = "Removed. Legion drops it at its next start.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
    removing.value = null;
  }
}
watch(editing, () => { tab.value = "general"; });
</script>

<template>
  <section id="mcp-servers" class="admin-panel-card" aria-labelledby="mcp-servers-title">
    <header class="admin-panel-head">
      <h2 id="mcp-servers-title" ref="panelTitle" tabindex="-1">MCP servers</h2>
      <div class="admin-panel-tools">
        <PanelHelp title="MCP servers">The MCP servers whose tools agents can use. Add a server, or open one to edit its address and see its tools.</PanelHelp>
        <button type="button" class="admin-icon accent" data-test="add" aria-label="Add server" title="Add server" :disabled="loading || !!loadError" @click="open('')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button>
        <AdminSearch ref="searchField" v-model="search" label="Search MCP servers" />
      </div>
    </header>
    <ActionMessage v-if="loadError" kind="error" :text="loadError" class="admin-panel-text"><button type="button" class="chip" @click="load">Retry</button></ActionMessage>
    <p v-if="!loaded && loading" class="admin-panel-text muted" role="status">Loading servers…</p>
    <p v-else-if="loaded && !rows.length" class="admin-panel-text muted" data-test="empty">
      {{ Object.keys(servers).length ? 'No servers match your search.' : 'No MCP servers configured.' }}
      <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button>
    </p>
    <div v-else-if="loaded" class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="mcp-servers-title">
      <table class="admin-records">
        <thead><tr><th scope="col">Name</th><th scope="col">{{ rows.some(([, server]) => server.transport === "stdio") ? "Connection URL or command" : "Connection URL" }}</th><th scope="col">Test</th><th scope="col">Result</th></tr></thead>
        <tbody>
          <tr v-for="[serverId, server] in rows" :key="serverId" :data-test="`row-${serverId}`">
            <th scope="row">
              <div class="admin-record-name">
                <span class="admin-record-badge" aria-hidden="true">{{ server.label.slice(0, 2).toUpperCase() }}</span>
                <div><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="selected = serverId">{{ server.label }}</button>
                  <p v-if="server.description">{{ server.description }}</p></div>
              </div>
            </th>
            <td><code>{{ endpoint(server) }}</code></td>
            <ConnectionTestCells :label="server.label" :run="() => agentsAdminClient.testServer(serverId)" />
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="notice" class="admin-panel-text muted" role="status" data-test="notice">{{ notice }}</p>

    <RecordDrawer ref="drawer" :open="selected !== null" :title="selected === '' ? 'Add server' : 'Server details'"
      :editable="!!selectedServer" :editing="editing !== null" :busy="saving" :fallback-focus="() => searchField?.focus()"
      @edit="selected && open(selected)" @discard="discard" @close="close" @save="save">
    <form v-if="editing !== null" id="mcp-server-editor" class="admin-editor" data-test="form" @submit.prevent="submit">
      <FormTabs v-model="tab" :items="tabItems" prefix="server" label="Server settings" />
      <section v-show="tab === 'general'" id="server-panel-general" class="pane" role="tabpanel" aria-labelledby="server-tab-general">
      <div class="field">
        <label for="server-id">Id</label>
        <input id="server-id" v-model="id" :disabled="!isNew || saving" autocomplete="off" spellcheck="false" data-test="id" />
        <p class="help">Lowercase letters, digits, - and _. Legion's main tool server is called <code>main</code>.</p>
      </div>
      <div class="field">
        <label for="server-label">Name</label>
        <input id="server-label" v-model="label" :disabled="saving" autocomplete="off" data-test="label" />
      </div>
      <div class="field">
        <label for="server-description">Description</label>
        <input id="server-description" v-model="description" :disabled="saving" autocomplete="off" data-test="description" maxlength="500" />
      </div>
      </section>
      <section v-show="tab === 'connection'" id="server-panel-connection" class="pane" role="tabpanel" aria-labelledby="server-tab-connection">
      <div class="field">
        <label for="server-transport">Connects by</label>
        <select id="server-transport" v-model="transport" :disabled="saving" data-test="transport">
          <option value="http">Web address (http)</option>
          <option value="stdio">Program on this machine (stdio)</option>
        </select>
      </div>
      <div v-if="transport === 'http'" class="field">
        <label for="server-mode">Connects to</label>
        <select id="server-mode" v-model="mode" :disabled="saving" data-test="mode">
          <option value="catalog">An outside service (saved in Treasury, backups allowed)</option>
          <option value="direct">One address (a Citadel service such as Armory)</option>
        </select>
      </div>
      <div v-if="transport === 'http' && mode === 'direct'" class="field">
        <label for="server-url">Address</label>
        <input id="server-url" v-model="url" type="url" inputmode="url" :disabled="saving" autocomplete="off" spellcheck="false" data-test="url" />
      </div>
      <template v-if="transport === 'http' && mode === 'catalog'">
        <fieldset v-for="(row, index) in addressRows" :key="row.key" class="field origin">
          <legend>{{ index === 0 ? "Address" : `Backup address ${index}` }}</legend>
          <input v-model="row.address" type="url" inputmode="url" :disabled="saving" autocomplete="off" spellcheck="false"
                 :aria-label="`Address ${index + 1}`" :data-test="`address-${index}`" @input="addressChanged(row)" @blur="check(row)" />
          <p v-if="row.unresolvedId" class="error" role="status">Address {{ row.unresolvedId }} is unavailable in Treasury. Enter its current URL or remove this address to save.</p>
          <input v-model="row.name" :disabled="saving || row.found === true" autocomplete="off"
                 :aria-label="`Service name for address ${index + 1}`" :data-test="`name-${index}`"
                 :placeholder="row.found === false ? 'Give this service a name' : 'Service name'" />
          <PasswordInput v-model="row.token" :label="`Token for address ${index + 1} (optional)`" :data-test="`override-${index}`" autocomplete="off" :disabled="saving"
                         :placeholder="row.overrideSet ? 'Leave empty to keep its saved token' : 'Empty uses the connection token below'" />
          <button v-if="(addressRows.length > 1 || row.unresolvedId)" type="button" class="chip" :disabled="saving" @click="removeAddress(index)">Remove address</button>
        </fieldset>
        <button type="button" class="chip" :disabled="saving || addressRows.length >= 10" data-test="add-address" @click="addAddress">Add a backup address</button>
        <p class="help">Legion tries the addresses in this order, switches only when one cannot be reached, and goes back when the first answers again.</p>
      </template>
      <template v-if="transport === 'stdio'">
        <div class="field">
          <label for="server-command">Command</label>
          <input id="server-command" v-model="command" :disabled="saving" autocomplete="off" spellcheck="false" data-test="command" />
        </div>
        <div class="field">
          <label for="server-args">Arguments</label>
          <input id="server-args" v-model="args" :disabled="saving" autocomplete="off" spellcheck="false" data-test="args" />
        </div>
      </template>
      <div v-if="transport === 'http'" class="field">
        <label for="server-header-name">Token header (optional)</label>
        <input id="server-header-name" v-model="headerName" :disabled="saving" autocomplete="off" spellcheck="false" placeholder="X-Internal-Token" data-test="header-name" />
      </div>
      <div v-if="transport === 'http' && headerName.trim()" class="field">
        <PasswordInput
          v-model="headerValue"
          label="Token"
          autocomplete="off"
          data-test="header-value"
          :disabled="saving"
          :placeholder="hadHeader ? 'Leave empty to keep the saved token' : 'Paste the token made for Legion'"
        />
        <p class="help">{{ hadHeader ? "A token is saved. It is never shown again." : "No token is saved yet." }}</p>
      </div>
      <p v-if="overrideNeedsConnectionToken" class="help">
        Set a connection token header and value to use address overrides.
      </p>
      </section>
      <ActionMessage v-if="error" kind="error" :text="error" />
    </form>
    <div v-else-if="selectedServer" class="admin-details">
      <h3>{{ selectedServer.label }}</h3>
      <p v-if="selectedServer.description">{{ selectedServer.description }}</p>
      <dl>
        <dt>ID</dt><dd><code>{{ selected }}</code></dd>
        <dt>{{ selectedServer.transport === "stdio" ? "Command" : "Connection URL" }}</dt><dd><code>{{ endpoint(selectedServer) }}</code></dd>
        <dt>Transport</dt><dd>{{ selectedServer.transport }}</dd>
        <template v-if="selectedServer.service_id"><dt>Catalog service</dt><dd><code>{{ selectedServer.service_id }}</code></dd></template>
        <template v-if="selectedServer.path"><dt>Path</dt><dd><code>{{ selectedServer.path }}</code></dd></template>
        <template v-if="selectedServer.origins?.length">
          <dt>Addresses tried in order</dt>
          <dd>
            <ol class="origins">
              <li v-for="origin in selectedServer.origins" :key="origin.origin_id">
                <code>{{ origin.origin || origin.origin_id }}</code>
                <span v-if="origin.has_override" class="muted"> (overridden here)</span>
              </li>
            </ol>
          </dd>
        </template>
        <dt>Authentication</dt>
        <dd>{{ selectedServer.auth?.type === "header"
          ? `Header ${selectedServer.auth.header_name ?? ""}, token ${selectedServer.auth.has_value ? "saved" : "not saved"}`
          : selectedServer.auth?.type === "env" ? `Environment variable ${selectedServer.auth.env_var ?? ""}`
          : "None" }}</dd>
      </dl>
      <p class="muted">{{ notice || "Changes take effect at Legion’s next start." }}</p>
      <ActionMessage v-if="error" kind="error" :text="error" />
      <button class="danger" type="button" data-test="remove" :disabled="saving" @click="removing = selected">Remove server</button>
    </div>
    <template v-if="editing !== null" #footer>
      <button type="button" class="chip" :disabled="saving" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
      <button type="submit" form="mcp-server-editor" class="primary" data-test="save" :disabled="saving || !valid" :aria-busy="saving">Save changes</button>
    </template>
    </RecordDrawer>

    <ConfirmModal
      :open="removing !== null"
      title="Remove server"
      :message="`Remove ${removing ?? ''}? Legion's agents lose its tools at the next start.`"
      confirm-label="Remove"
      danger
      :busy="saving"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.pane { display: grid; gap: 12px; min-width: 0; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .field > select { width: 100%; min-width: 0; min-height: 44px; }
.origin { gap: 8px; margin: 0; padding: 0; border: 0; }
.origin legend { font-size: 0.9em; font-weight: 600; padding: 0; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.origins { margin: 0; padding: 0; list-style: none; }
</style>
