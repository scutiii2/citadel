<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import type { ModelGatewayField, ModelGatewayKind, ModelGatewayList, ModelGatewayRow } from "../api/AgentsAdminClient";
import { AdminSearch } from "@citadel/ui";
import { ConfirmModal } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { RecordDrawer } from "@citadel/ui";
import ConnectionTestCells from "./ConnectionTestCells.vue";
import FieldLabel from "./FieldLabel.vue";
import FormTabs from "./admin/FormTabs.vue";
import { PasswordInput } from "@citadel/ui";
import { ToggleSwitch } from "@citadel/ui";
import { errorMessage } from "../utils/errors";

const props = defineProps<{ kind: ModelGatewayKind; title: string; help: string }>();
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();

const list = ref<ModelGatewayList>();
const loading = ref(false);
const loadError = ref("");
const open = ref(false);
const editing = ref(false);
const creating = ref(false);
const selected = ref<ModelGatewayRow>();
const removing = ref(false);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const drawer = ref<InstanceType<typeof RecordDrawer>>();

const id = ref("");
const type = ref("");
const auth = ref("key");
const model = ref("");
const api = ref("chat");
const timeout = ref(0);
const trusted = ref(false);
const hearsAudio = ref(false);
const TIERS = ["light", "standard", "heavy", "extreme"] as const;
const tiers = ref<Record<string, string>>({});
const notes = ref<Record<string, string>>({});
const values = ref<Record<string, string>>({});
const secrets = ref<Record<string, string>>({});
// Preset keys the form has no input for (label, capabilities, token limits) travel along unchanged.
const extra = ref<Record<string, unknown>>({});
const preset = ref("");
const testing = ref(false);
const draftTest = ref<{ ok: boolean; code: string; message: string } | null>(null);
const tab = ref("connection");

const chat = computed(() => props.kind === "conversation");
const types = computed(() => Object.keys(chat.value ? list.value?.form?.providers ?? {} : list.value?.kinds ?? {}));
const variants = computed(() => Object.keys(list.value?.form?.providers[type.value] ?? {}).filter((name) => name !== ""));
const fields = computed<ModelGatewayField[]>(() => {
  if (!chat.value) return list.value?.kinds?.[type.value] ?? [];
  return list.value?.form?.providers[type.value]?.[type.value === "scuti" ? "" : auth.value] ?? [];
});
// Chat gateways other than Scuti services name their model outside the variant fields; decision kinds list it among them.
const needsModel = computed(() => chat.value && type.value !== "" && type.value !== "scuti");
const GROUP_TITLES: Record<string, string> = {
  anthropic: "Anthropic protocol", openai: "OpenAI protocol", scuti: "Model services",
  typesafe: "TypeSafe", ollama: "Ollama", freellmapi: "FreeLLMAPI",
};
// Presets grouped by what they talk to, each group sorted by name.
const presetGroups = computed(() => {
  const groups = new Map<string, { key: string; label: string }[]>();
  for (const [key, value] of Object.entries(list.value?.presets ?? {})) {
    const group = String(value[chat.value ? "provider" : "kind"] ?? "other");
    groups.set(group, [...(groups.get(group) ?? []), { key, label: String(value.label ?? key) }]);
  }
  const order = Object.keys(GROUP_TITLES);
  const rank = (group: string) => (order.includes(group) ? order.indexOf(group) : order.length);
  return [...groups].sort(([a], [b]) => rank(a) - rank(b)).map(([group, items]) => ({ group, title: GROUP_TITLES[group] ?? group, items: items.sort((a, b) => a.label.localeCompare(b.label)) }));
});
const presets = computed(() => presetGroups.value.flatMap((entry) => entry.items));
// What each field means, shown in the help popover beside its label.
const FIELD_HELP: Record<string, string[]> = {
  api_key: ["The secret key from the provider's dashboard. It is kept in Legion's database and never shown again.", "When editing, leave it empty to keep the saved key."],
  token: ["The access token the service expects, if it needs one. Kept in Legion's database and never shown again."],
  base_url: ["Where requests go. Empty uses the provider's own address.", "Set it for gateways such as OpenRouter, or a local server such as Ollama (http://host.docker.internal:11434/v1)."],
  aws_region: ["The AWS region that serves your Bedrock models, for example us-east-1."],
  aws_access_key_id: ["The access key id of an AWS user allowed to call Bedrock."],
  aws_secret_access_key: ["The secret that goes with the access key id. Never shown again."],
  project_id: ["The Google Cloud project that has Vertex AI enabled."],
  region: ["The Google Cloud region that serves your models, for example us-east5."],
  azure_endpoint: ["The address of your Azure OpenAI resource, for example https://name.openai.azure.com."],
  api_version: ["The Azure OpenAI API version to call, for example 2025-04-01-preview."],
  url: ["The address of the service. A service running on this computer is reached at host.docker.internal."],
  project: ["The model name this service runs. Leave empty to use its default."],
  model: ["The model id sent with each request."],
  strategy: ["How the service reads long input. Leave empty for the default."],
  window: ["How many tokens of input the service reads at once. Leave empty for the default."],
};
const fieldHelp = (name: string) => FIELD_HELP[name];
// Where the chosen preset's provider lists its model names.
const modelsUrl = computed(() => {
  const found = (key: string) => list.value?.presets?.[key]?.models_url;
  const url = found(preset.value) ?? found(id.value);
  return typeof url === "string" ? url : "";
});
// A new chat gateway gets its models from a preset, so the Models tab waits for one.
const modelsLocked = computed(() => needsModel.value && creating.value && !preset.value);
const tabItems = computed(() => [
  { id: "connection", label: "Connection" },
  { id: "models", label: "Models", disabled: modelsLocked.value, title: modelsLocked.value ? "Choose a preset on the Connection tab first" : undefined },
]);
const typeKey = computed(() => (chat.value ? "provider" : "kind"));

const rows = computed(() => (list.value?.gateways ?? []).filter((row) => {
  const needle = search.value.trim().toLowerCase();
  return !needle || [row.id, row.label, row.model, row.provider, row.kind].some((value) => String(value ?? "").toLowerCase().includes(needle));
}));

async function load() {
  if (loading.value) return;
  loading.value = true;
  loadError.value = "";
  try {
    list.value = await agentsAdminClient.modelGateways(props.kind);
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function fill(source: Record<string, unknown>) {
  draftTest.value = null;
  type.value = String(source[typeKey.value] ?? types.value[0] ?? "");
  auth.value = String(source.auth ?? "key");
  model.value = String(source.model ?? "");
  api.value = String(source.api ?? "chat");
  timeout.value = Number(source.timeout_s ?? 0);
  trusted.value = source.trusted === true;
  hearsAudio.value = (source.capabilities as Record<string, unknown> | undefined)?.audio === true;
  values.value = {};
  secrets.value = {};
  const models = source.models && typeof source.models === "object" ? source.models as Record<string, unknown> : {};
  tiers.value = Object.fromEntries(TIERS.map((tier) => [tier, String(models[tier] ?? "")]));
  const described = source.descriptions && typeof source.descriptions === "object" ? source.descriptions as Record<string, unknown> : {};
  notes.value = Object.fromEntries(TIERS.map((tier) => [tier, String(described[tier] ?? "")]));
  for (const [name, , secret] of fields.value) if (!secret) values.value[name] = String(source[name] ?? "");
  const known = new Set([typeKey.value, "auth", "model", "models", "descriptions", "api", "timeout_s", "trusted", ...fields.value.map(([name]) => name)]);
  extra.value = Object.fromEntries(Object.entries(source).filter(([name]) => !known.has(name) && !name.startsWith("has_") && name !== "id" && name !== "reachable" && name !== "streams" && name !== "images" && name !== "audio" && name !== "types"));
}

function add() {
  tab.value = "connection";
  creating.value = true;
  selected.value = undefined;
  id.value = "";
  preset.value = "";
  error.value = notice.value = "";
  fill({});
  editing.value = true;
  open.value = true;
}

function startFrom() {
  const chosen = list.value?.presets[preset.value];
  if (!chosen) {
    tab.value = "connection";
    return;
  }
  if (!id.value) id.value = preset.value;
  fill(chosen);
}

function show(row: ModelGatewayRow) {
  creating.value = false;
  selected.value = row;
  notice.value = "";
  open.value = true;
}

function edit() {
  if (!selected.value) return;
  tab.value = "connection";
  error.value = notice.value = "";
  id.value = selected.value.id;
  fill(selected.value);
  editing.value = true;
}

function discard() {
  editing.value = false;
  secrets.value = {};
  if (creating.value) open.value = false;
}

function close() {
  editing.value = false;
  secrets.value = {};
  open.value = false;
}

const entry = computed(() => {
  const body: Record<string, unknown> = { ...extra.value, [typeKey.value]: type.value };
  if (chat.value && type.value !== "scuti") body.auth = auth.value;
  if (needsModel.value) body.model = model.value.trim();
  if (chat.value && type.value === "openai") body.api = api.value;
  if (needsModel.value) body.models = Object.fromEntries(TIERS.map((tier) => [tier, (tiers.value[tier] ?? "").trim()]).filter(([, name]) => name));
  if (needsModel.value) body.descriptions = Object.fromEntries(TIERS.map((tier) => [tier, (notes.value[tier] ?? "").trim()]).filter(([, text]) => text));
  if (timeout.value) body.timeout_s = timeout.value;
  body.trusted = trusted.value;
  if (chat.value && type.value === "openai" && api.value === "chat") {
    body.capabilities = { ...(extra.value.capabilities as object | undefined), audio: hearsAudio.value };
  }
  for (const [name, , secret] of fields.value) {
    if (secret) { if (secrets.value[name]) body[name] = secrets.value[name]; } else body[name] = (values.value[name] ?? "").trim();
  }
  return body;
});

/** Try the form as filled in, before saving. A saved secret left empty stays; the name is only needed to find it. */
async function testDraft() {
  if (testing.value || saving.value) return;
  draftTest.value = null;
  const missing = fields.value.find(([name, , secret, required]) => required && !secret && !(values.value[name] ?? "").trim());
  if (missing) {
    tab.value = "connection";
    draftTest.value = { ok: false, code: "SETUP", message: `${missing[1]} is required.` };
    return;
  }
  if (needsModel.value && !model.value.trim()) {
    tab.value = "models";
    draftTest.value = { ok: false, code: "SETUP", message: "Enter a default model first." };
    return;
  }
  testing.value = true;
  try {
    const gid = /^[a-z0-9][a-z0-9_-]{0,47}$/.test(id.value) ? id.value : "draft";
    const result = await agentsAdminClient.testModelGateway(props.kind, gid, entry.value);
    draftTest.value = { ok: result.ok, code: result.code ?? (result.ok ? "" : "ERR"), message: result.message };
  } catch (err) {
    draftTest.value = { ok: false, code: "ERR", message: errorMessage(err) };
  } finally {
    testing.value = false;
  }
}

function submit() {
  if (saving.value) return;
  if (!/^[a-z0-9][a-z0-9_-]{0,47}$/.test(id.value)) {
    tab.value = "connection";
    error.value = "The name needs lowercase letters, digits, - or _, up to 48 characters.";
    return;
  }
  if (needsModel.value && creating.value && !preset.value) {
    tab.value = "connection";
    error.value = "Choose a preset first.";
    return;
  }
  const missing = fields.value.find(([name, , secret, required]) => required && !secret && !(values.value[name] ?? "").trim());
  if (missing) {
    tab.value = "connection";
    error.value = `${missing[1]} is required.`;
    return;
  }
  if (needsModel.value && !model.value.trim()) {
    tab.value = "models";
    error.value = "Enter a default model.";
    return;
  }
  error.value = "";
  drawer.value?.requestSave();
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const saved = await agentsAdminClient.saveModelGateway(props.kind, id.value, entry.value);
    await load();
    selected.value = list.value?.gateways.find((row) => row.id === saved.id) ?? saved;
    creating.value = false;
    editing.value = false;
    secrets.value = {};
    notice.value = "Saved. Agents use it within a minute.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!selected.value) return;
  saving.value = true;
  try {
    await agentsAdminClient.removeModelGateway(props.kind, selected.value.id);
    removing.value = false;
    open.value = false;
    await load();
  } catch (err) {
    removing.value = false;
    notice.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

const healthOf = (row: ModelGatewayRow) => row.health as { cooldown_seconds: number; failures_24h: number; last_kind: string | null } | undefined;
const minutes = (seconds: number) => (seconds < 90 ? `for ${seconds} s` : `for ${Math.round(seconds / 60)} min`);
const hasSecret = (name: string) => Boolean(selected.value?.[`has_${name}`]) && !creating.value;
const summary = (row: ModelGatewayRow) => String(row.model ?? row.project ?? row.url ?? row.base_url ?? "");
const drawerTitle = computed(() => (creating.value ? `Add ${props.title.toLowerCase()} gateway` : selected.value?.id ?? props.title));

onMounted(load);
</script>

<template>
  <section :id="`${kind}-gateways`" class="admin-panel-card" :aria-labelledby="`${kind}-gateways-title`">
    <header class="admin-panel-head">
      <h2 :id="`${kind}-gateways-title`">{{ title }}</h2>
      <div class="admin-panel-tools">
        <PanelHelp :title="title">{{ help }}</PanelHelp>
        <button type="button" class="admin-icon accent" :data-test="`add-${kind}`" :aria-label="`Add ${title.toLowerCase()} gateway`"
          :title="`Add ${title.toLowerCase()} gateway`" :disabled="!list" @click="add">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        </button>
        <AdminSearch ref="searchField" v-model="search" :label="`Search ${title.toLowerCase()}`" />
      </div>
    </header>
    <ActionMessage v-if="loadError" kind="error" :text="loadError" class="admin-panel-text"><button type="button" class="chip" @click="load">Retry</button></ActionMessage>
    <p v-else-if="loading && !list" class="admin-panel-text muted" role="status">Loading…</p>
    <p v-else-if="list && !rows.length" class="admin-panel-text muted" :data-test="`empty-${kind}`">
      {{ list.gateways.length ? "No gateways match your search." : "No gateway is saved yet. Use + to add one." }}
      <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button>
    </p>
    <div v-else-if="list" class="admin-table-scroll" tabindex="0" role="region" :aria-labelledby="`${kind}-gateways-title`">
      <table class="admin-records">
        <thead><tr><th scope="col">Name</th><th scope="col">{{ chat ? "Provider and model" : "Kind and address" }}</th><th scope="col">Test</th><th scope="col">Result</th><th v-if="chat" scope="col">Health</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <th scope="row">
              <div class="admin-record-name">
                <span class="admin-record-badge" aria-hidden="true">{{ row.id.slice(0, 2).toUpperCase() }}</span>
                <div>
                  <button type="button" class="admin-row-button" aria-haspopup="dialog" @click="show(row)">{{ row.id }}</button>
                  <p v-if="row.label">{{ row.label }}</p>
                  <p class="trust" :class="{ on: row.trusted }" :data-test="`trust-${row.id}`">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path v-if="row.trusted" d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.500-7-10V6z M9 12l2 2 4-4" /><path v-else d="M12 3l7 3v5c0 4.500-3 8-7 10-4-2-7-5.500-7-10V6z" /></svg>{{ row.trusted ? "Trusted" : "Not trusted" }}
                  </p>
                </div>
              </div>
            </th>
            <td><code>{{ summary(row) || "—" }}</code><p class="kind">{{ row.provider ?? row.kind }}</p></td>
            <ConnectionTestCells :label="row.id" :run="() => agentsAdminClient.testModelGateway(kind, row.id)" />
            <td v-if="chat" :data-test="`health-${row.id}`">
              <p v-if="healthOf(row)?.cooldown_seconds" class="health bad">
                <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>Cooling down {{ minutes(healthOf(row)!.cooldown_seconds) }}
                <PanelHelp :title="`${row.id} is cooling down`">Its last call failed ({{ healthOf(row)?.last_kind?.replace('_', ' ') }}), so agents skip it until the time is up and use their other gateways. A restart does not clear it.</PanelHelp>
              </p>
              <p v-else-if="healthOf(row)?.failures_24h" class="health warn">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l9 16H3z M12 10v4 M12 17h.01" /></svg>{{ healthOf(row)!.failures_24h }} failure{{ healthOf(row)!.failures_24h === 1 ? "" : "s" }} in 24 hours
              </p>
              <p v-else class="health muted">No failures in 24 hours</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
  <Teleport to="body">
    <RecordDrawer ref="drawer" :open="open" :title="drawerTitle" editable :editing="editing" :busy="saving" :note="editing && !type ? 'Choose a gateway type first.' : ''" :fallback-focus="() => searchField?.focus()"
      @edit="edit" @close="close" @discard="discard" @save="save">
      <form v-if="editing" :id="`${kind}-editor`" class="admin-editor" novalidate @submit.prevent="submit">
        <FormTabs v-if="needsModel" v-model="tab" :items="tabItems" :prefix="kind" :label="`${title} settings`" />
        <section v-show="!needsModel || tab === 'connection'" :id="`${kind}-panel-connection`" class="pane" role="tabpanel" :aria-labelledby="`${kind}-tab-connection`">
          <template v-if="creating && presets.length">
            <FieldLabel :for="`${kind}-preset`" title="Preset" :help="['Fills the connection and the models for a known provider.', 'Choose one first: the Models tab stays locked until you do. Change any field afterwards if yours differs.']">Preset</FieldLabel>
            <select :id="`${kind}-preset`" v-model="preset" data-test="preset" :disabled="saving" @change="startFrom">
              <option value="">None</option>
              <optgroup v-for="entry in presetGroups" :key="entry.group" :label="entry.title">
                <option v-for="item in entry.items" :key="item.key" :value="item.key">{{ item.label }}</option>
              </optgroup>
            </select>
          </template>
          <FieldLabel :for="`${kind}-id`" title="Name" :help="['The short name agents and logs use for this gateway: lowercase letters, digits, - and _.', 'It cannot be changed after saving.']">Name</FieldLabel>
          <input :id="`${kind}-id`" v-model="id" maxlength="48" autocomplete="off" spellcheck="false" data-test="id" :disabled="saving || !creating" />
          <div class="pair">
            <div>
              <FieldLabel :for="`${kind}-type`" :title="chat ? 'Provider' : 'Kind'"
                :help="chat ? ['The protocol Legion speaks to this gateway.', 'anthropic: Claude and gateways that copy its API. openai: GPT and any OpenAI-compatible server. scuti: Citadel model services.'] : ['Which kind of decision service this is: TypeSafe, Ollama, a Citadel model service or FreeLLMAPI.']">{{ chat ? "Provider" : "Kind" }}</FieldLabel>
              <select :id="`${kind}-type`" v-model="type" data-test="type" :disabled="saving || !creating" @change="fill({ [typeKey]: type })">
                <option v-for="name in types" :key="name" :value="name">{{ name }}</option>
              </select>
            </div>
            <div v-if="chat && variants.length">
              <FieldLabel :for="`${kind}-auth`" title="Sign-in" :help="['How Legion proves who it is to the provider.', 'key: an API key. bedrock: AWS credentials. vertex: a Google Cloud project. azure: an Azure resource and key.']">Sign-in</FieldLabel>
              <select :id="`${kind}-auth`" v-model="auth" data-test="auth" :disabled="saving">
                <option v-for="name in variants" :key="name" :value="name">{{ name }}</option>
              </select>
            </div>
            <div v-if="chat && type === 'openai'">
              <FieldLabel :for="`${kind}-api`" title="API style" :help="[
                'Which OpenAI endpoint the gateway calls.',
                'chat uses Chat Completions (/v1/chat/completions). Every OpenAI-compatible server supports it: Ollama, Groq, OpenRouter, vLLM, LiteLLM and so on.',
                'responses uses the newer Responses API (/v1/responses). Only OpenAI itself and Azure OpenAI support it reliably.',
                'Choose responses for GPT and Azure OpenAI, chat for any other server or custom base address. A preset sets the right one.']">API style</FieldLabel>
              <select :id="`${kind}-api`" v-model="api" :disabled="saving">
                <option v-for="name in list?.form?.choices.api ?? []" :key="name" :value="name">{{ name }}</option>
              </select>
            </div>
          </div>
          <template v-for="[name, label, secret, required] in fields" :key="name">
            <PasswordInput v-if="secret" v-model="secrets[name]" :label="label" autocomplete="off" :data-test="name" :disabled="saving"
              :placeholder="hasSecret(name) ? 'Leave empty to keep the saved value' : 'Paste it here; kept in Legion’s database, never shown again'">
              <template v-if="fieldHelp(name)" #help><PanelHelp :title="label"><p v-for="line in fieldHelp(name)" :key="line">{{ line }}</p></PanelHelp></template>
            </PasswordInput>
            <template v-else>
              <FieldLabel :for="`${kind}-${name}`" :title="label" :help="fieldHelp(name)">{{ label }}<span v-if="required" class="req" aria-hidden="true"> *</span></FieldLabel>
              <input :id="`${kind}-${name}`" v-model="values[name]" autocomplete="off" spellcheck="false" :aria-required="required" :data-test="name" :disabled="saving" />
            </template>
          </template>
          <FieldLabel :for="`${kind}-timeout`" title="Time allowed" :help="['How many seconds one request may take before Legion gives up on it.', 'Zero uses the gateway default.']">Time allowed (seconds)</FieldLabel>
          <input :id="`${kind}-timeout`" v-model.number="timeout" type="number" min="0" max="1800" :disabled="saving" :aria-describedby="`${kind}-timeout-help`" />
          <p :id="`${kind}-timeout-help`" class="hint">0 uses the gateway's default.</p>
          <FieldLabel :for="`${kind}-trusted`" title="Trusted" :help="['Marks this gateway as safe for confidential data: passwords, personal identifiers, private messages and documents.', 'When a request holds such data, Legion uses only trusted gateways. Every agent keeps at least one trusted gateway, so the last one cannot be switched off.']">Trusted for confidential data</FieldLabel>
          <ToggleSwitch :id="`${kind}-trusted`" data-test="trusted" :checked="trusted" :disabled="saving" @change="trusted = ($event.target as HTMLInputElement).checked">{{ trusted ? "Trusted" : "Not trusted" }}</ToggleSwitch>
          <template v-if="chat && type === 'openai' && api === 'chat'">
            <FieldLabel :for="`${kind}-audio`" title="Hears audio" :help="['Switch on only when the model of this gateway accepts audio input.', 'The transcriber agent needs such a gateway when Scribe cannot transcribe a file.']">Hears audio</FieldLabel>
            <ToggleSwitch :id="`${kind}-audio`" data-test="audio" :checked="hearsAudio" :disabled="saving" @change="hearsAudio = ($event.target as HTMLInputElement).checked">{{ hearsAudio ? "Hears audio" : "No audio" }}</ToggleSwitch>
          </template>
        </section>
        <section v-if="needsModel" v-show="tab === 'models'" :id="`${kind}-panel-models`" class="pane" role="tabpanel" :aria-labelledby="`${kind}-tab-models`">
          <p v-if="modelsUrl" class="hint"><a :href="modelsUrl" target="_blank" rel="noopener noreferrer" data-test="models-link">Browse the model list for this provider</a> to find the ids to enter below.</p>
          <FieldLabel :for="`${kind}-model`" title="Default model" :help="['The model id used when an agent names no tier.', 'Copy it exactly from the provider model list.']">Default model</FieldLabel>
          <input :id="`${kind}-model`" v-model="model" maxlength="200" autocomplete="off" spellcheck="false" data-test="model" :disabled="saving" />
          <p class="hint">Used when an agent names no tier. The tiers below are optional: an empty model uses the default, an empty description keeps the built-in one. Agents that delegate read the descriptions to pick the lightest tier that fits a task.</p>
          <div v-for="tier in TIERS" :key="tier" class="tier">
            <h4>{{ tier[0]?.toUpperCase() }}{{ tier.slice(1) }}</h4>
            <FieldLabel :for="`${kind}-tier-${tier}`" :title="`${tier} model`" :help="['The model id used for this tier. Empty uses the default model.', 'Agents pick a tier by how hard the task is: lighter tiers are cheaper and faster.']">Model<span class="sr-only"> for {{ tier }}</span></FieldLabel>
            <input :id="`${kind}-tier-${tier}`" v-model="tiers[tier]" maxlength="200" autocomplete="off" spellcheck="false" :data-test="`tier-${tier}`" :disabled="saving" />
            <FieldLabel :for="`${kind}-note-${tier}`" :title="`When to use ${tier}`" :help="['What this tier is good for. Agents that delegate read it to choose the lightest tier that fits a task.', 'Empty keeps the built-in description.']">When to use<span class="sr-only"> {{ tier }}</span></FieldLabel>
            <input :id="`${kind}-note-${tier}`" v-model="notes[tier]" maxlength="300" autocomplete="off" :data-test="`note-${tier}`" :disabled="saving" placeholder="Built-in description" />
          </div>
        </section>
        <ActionMessage v-if="error" kind="error" :text="error" data-test="error" />
        <p v-if="draftTest" class="draft-test" :class="draftTest.ok ? 'ok' : 'bad'" role="status" data-test="draft-result">
          <svg v-if="draftTest.ok" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.7 2.7L16 9.8" /></svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9 9l6 6M15 9l-6 6" /></svg>
          <code v-if="!draftTest.ok" class="code" data-test="draft-code">{{ draftTest.code }}</code>
          <span>{{ draftTest.message }}</span>
        </p>
      </form>
      <div v-else-if="open && selected" class="admin-details">
        <dl>
          <dt>{{ chat ? "Provider" : "Kind" }}</dt><dd>{{ selected.provider ?? selected.kind }}</dd>
          <template v-if="summary(selected)"><dt>{{ selected.model ? "Model" : "Address" }}</dt><dd><code>{{ summary(selected) }}</code></dd></template>
          <dt>ID</dt><dd><code>{{ selected.id }}</code></dd>
          <template v-if="selected.label && selected.label !== selected.id"><dt>Label</dt><dd>{{ selected.label }}</dd></template>
          <template v-if="selected.auth"><dt>Authentication</dt><dd>{{ selected.auth }}</dd></template>
          <template v-if="selected.timeout_s"><dt>Timeout</dt><dd>{{ selected.timeout_s }} seconds</dd></template>
          <dt>Trusted</dt><dd>{{ selected.trusted ? "Yes: may see confidential data" : "No: never sees confidential data" }}</dd>
          <dt>Reachable</dt><dd>{{ selected.reachable === undefined ? "Not checked" : selected.reachable ? "Yes" : "No" }}</dd>
        </dl>
        <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
        <section class="danger-zone">
          <h4>Danger zone</h4>
          <button type="button" class="danger" data-test="remove" @click="removing = true">Delete this gateway</button>
        </section>
      </div>
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="saving || testing" data-test="test-draft" :aria-busy="testing" title="Check the connection before saving" @click="testDraft">Test</button>
        <button type="button" class="chip" :disabled="saving" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="submit" :form="`${kind}-editor`" class="primary" data-test="save" :disabled="saving || !type" :aria-busy="saving">Save</button>
      </template>
    </RecordDrawer>
    <ConfirmModal :open="removing" title="Delete gateway" :message="`Delete ${selected?.id ?? ''}? Agents that use it stop working until another gateway has its name.`"
      confirm-label="Delete" danger :busy="saving" @confirm="remove" @close="removing = false" />
  </Teleport>
</template>

<style scoped>
.admin-panel-card { margin-bottom: 14px; }
.kind { margin: 2px 0 0; font-size: 0.8rem; color: var(--muted); }
.health { display: flex; align-items: center; gap: 4px; margin: 0; font-size: 0.85rem; }
.health svg { flex: none; width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.health.bad { color: var(--danger); }
.health.warn { color: var(--warning); }
.trust { display: flex; align-items: center; gap: 4px; margin: 2px 0 0; font-size: 0.8rem; color: var(--muted); }
.trust.on { color: var(--success); }
.trust svg { flex: none; width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.pane { display: grid; gap: 6px; min-width: 0; }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.pair > div { display: grid; gap: 6px; min-width: 0; }
.tier { display: grid; gap: 6px; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.tier h4 { margin: 0; font-size: 0.9rem; }
.draft-test { display: flex; align-items: flex-start; gap: 8px; margin: 0; overflow-wrap: anywhere; }
.draft-test svg { flex: none; width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.draft-test.ok { color: var(--success); }
.draft-test.bad { color: var(--danger); }
.draft-test .code { flex: none; padding: 1px 6px; border: 1px solid currentColor; border-radius: var(--radius-sm); font-size: 0.8rem; font-weight: 600; }
.draft-test span { color: var(--text); }
.hint { margin: 0; font-size: 0.85rem; color: var(--muted); }
.req { color: var(--accent); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
