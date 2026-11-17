<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { agentsAdminClient, type McpServer } from "../api/AgentsAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PageLayout from "../components/PageLayout.vue";
import PasswordInput from "../components/PasswordInput.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

/** The MCP servers Legion's agents use as tools. Saved in Legion's database; a change applies at Legion's next start.
 * The header value of a server is write-only: the server only says whether one is saved. */
const servers = ref<Record<string, McpServer>>({});
const loading = ref(true);
const error = ref("");
const notice = ref("");
const saving = ref(false);

const editing = ref<string | null>(null); // the id being edited; "" while adding
const id = ref("");
const label = ref("");
const description = ref("");
const transport = ref<"http" | "stdio">("http");
const url = ref("");
const command = ref("");
const args = ref("");
const headerName = ref("");
const headerValue = ref("");
const hadHeader = ref(false);
const removing = ref<string | null>(null);

const rows = computed(() => Object.entries(servers.value).sort(([a], [b]) => a.localeCompare(b)));
const isNew = computed(() => editing.value === "");
const valid = computed(
  () =>
    /^[a-z0-9][a-z0-9_-]{0,62}$/.test(id.value) &&
    label.value.trim() !== "" &&
    (transport.value === "http" ? url.value.trim() !== "" : command.value.trim() !== ""),
);

async function load() {
  try {
    servers.value = await agentsAdminClient.servers();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function open(serverId: string) {
  const server = serverId ? servers.value[serverId] : undefined;
  editing.value = serverId;
  id.value = serverId;
  label.value = server?.label ?? "";
  description.value = server?.description ?? "";
  transport.value = server?.transport ?? "http";
  url.value = server?.url ?? "";
  command.value = server?.command ?? "";
  args.value = (server?.args ?? []).join(" ");
  headerName.value = server?.auth?.type === "header" ? (server.auth.header_name ?? "") : "";
  hadHeader.value = server?.auth?.type === "header" && !!server.auth.has_value;
  headerValue.value = "";
  error.value = notice.value = "";
}

function close() {
  editing.value = null;
}

/** An untouched header value is left out, so the stored one stays. */
function entry(): McpServer {
  const body: McpServer = { label: label.value.trim(), description: description.value.trim(), transport: transport.value };
  if (transport.value === "http") body.url = url.value.trim();
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
  saving.value = true;
  error.value = notice.value = "";
  try {
    await agentsAdminClient.saveServer(id.value, entry());
    await load();
    notice.value = "Saved. Legion uses the change at its next start.";
    close();
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
    await load();
    notice.value = "Removed. Legion drops it at its next start.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
    removing.value = null;
  }
}
</script>

<template>
  <PageLayout
    class="info-content servers"
    title="MCP servers"
    description="The tool servers Legion's agents connect to, such as Armory. They are saved in Legion's database and a change applies at Legion's next start."
  >
    <template #actions>
      <button type="button" class="primary" data-test="add" @click="open('')">Add server</button>
    </template>

    <p v-if="error && editing === null" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!rows.length" class="muted" data-test="empty">
      No server yet. Add Armory (for example http://127.0.0.1:29600/mcp) as <code>main</code> so the agents get tools.
    </p>

    <table v-else>
      <thead>
        <tr><th>Id</th><th>Name</th><th>Where</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="[serverId, server] in rows" :key="serverId" :data-test="`row-${serverId}`">
          <td><code>{{ serverId }}</code></td>
          <td>{{ server.label }}<span v-if="server.description" class="muted"> — {{ server.description }}</span></td>
          <td>{{ server.transport === "http" ? server.url : `${server.command} ${(server.args ?? []).join(" ")}` }}</td>
          <td class="row-actions">
            <button type="button" class="chip" data-test="edit" @click="open(serverId)">Edit</button>
            <button type="button" class="danger" data-test="remove" @click="removing = serverId">Remove</button>
          </td>
        </tr>
      </tbody>
    </table>

    <form v-if="editing !== null" class="card" data-test="form" @submit.prevent="save">
      <h2 class="title">{{ isNew ? "Add server" : `Edit ${editing}` }}</h2>
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
        <input id="server-description" v-model="description" :disabled="saving" autocomplete="off" data-test="description" />
      </div>
      <div class="field">
        <label for="server-transport">Connects by</label>
        <select id="server-transport" v-model="transport" :disabled="saving" data-test="transport">
          <option value="http">Web address (http)</option>
          <option value="stdio">Program on this machine (stdio)</option>
        </select>
      </div>
      <div v-if="transport === 'http'" class="field">
        <label for="server-url">Address</label>
        <input id="server-url" v-model="url" type="url" inputmode="url" :disabled="saving" autocomplete="off" spellcheck="false" data-test="url" />
      </div>
      <template v-else>
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
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="button" class="chip" :disabled="saving" @click="close">Cancel</button>
        <button type="submit" class="primary" data-test="save" :disabled="saving || !valid">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>

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
  </PageLayout>
</template>

<style scoped>
.card {
  display: grid;
  gap: 12px;
  max-width: 560px;
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.title { margin: 0; font-size: 1em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .field > select { width: 100%; min-width: 0; min-height: 44px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.actions, .row-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions { justify-content: flex-end; }
</style>
