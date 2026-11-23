<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import type { ModelGatewayField, ModelGatewayKind, ModelGatewayList, ModelGatewayRow } from "../api/AgentsAdminClient";
import AdminSearch from "./admin/AdminSearch.vue";
import ConfirmModal from "./admin/ConfirmModal.vue";
import PanelHelp from "./admin/PanelHelp.vue";
import RecordDrawer from "./admin/RecordDrawer.vue";
import ConnectionTest from "./ConnectionTest.vue";
import PasswordInput from "./PasswordInput.vue";
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
const TIERS = ["light", "standard", "heavy", "extreme"] as const;
const tiers = ref<Record<string, string>>({});
const notes = ref<Record<string, string>>({});
const values = ref<Record<string, string>>({});
const secrets = ref<Record<string, string>>({});
// Preset keys the form has no input for (label, capabilities, token limits) travel along unchanged.
const extra = ref<Record<string, unknown>>({});
const preset = ref("");

const chat = computed(() => props.kind === "conversation");
const types = computed(() => Object.keys(chat.value ? list.value?.form?.providers ?? {} : list.value?.kinds ?? {}));
const variants = computed(() => Object.keys(list.value?.form?.providers[type.value] ?? {}).filter((name) => name !== ""));
const fields = computed<ModelGatewayField[]>(() => {
  if (!chat.value) return list.value?.kinds?.[type.value] ?? [];
  return list.value?.form?.providers[type.value]?.[type.value === "scuti" ? "" : auth.value] ?? [];
});
// Chat gateways other than Scuti services name their model outside the variant fields; decision kinds list it among them.
const needsModel = computed(() => chat.value && type.value !== "" && type.value !== "scuti");
const presets = computed(() => Object.entries(list.value?.presets ?? {}).map(([key, value]) => ({ key, label: String(value.label ?? key) })));
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
  type.value = String(source[typeKey.value] ?? types.value[0] ?? "");
  auth.value = String(source.auth ?? "key");
  model.value = String(source.model ?? "");
  api.value = String(source.api ?? "chat");
  timeout.value = Number(source.timeout_s ?? 0);
  values.value = {};
  secrets.value = {};
  const models = source.models && typeof source.models === "object" ? source.models as Record<string, unknown> : {};
  tiers.value = Object.fromEntries(TIERS.map((tier) => [tier, String(models[tier] ?? "")]));
  const described = source.descriptions && typeof source.descriptions === "object" ? source.descriptions as Record<string, unknown> : {};
  notes.value = Object.fromEntries(TIERS.map((tier) => [tier, String(described[tier] ?? "")]));
  for (const [name, , secret] of fields.value) if (!secret) values.value[name] = String(source[name] ?? "");
  const known = new Set([typeKey.value, "auth", "model", "models", "descriptions", "api", "timeout_s", ...fields.value.map(([name]) => name)]);
  extra.value = Object.fromEntries(Object.entries(source).filter(([name]) => !known.has(name) && !name.startsWith("has_") && name !== "id" && name !== "reachable" && name !== "streams" && name !== "images" && name !== "types"));
}

function add() {
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
  if (!chosen) return;
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
  for (const [name, , secret] of fields.value) {
    if (secret) { if (secrets.value[name]) body[name] = secrets.value[name]; } else body[name] = (values.value[name] ?? "").trim();
  }
  return body;
});

function submit() {
  if (saving.value) return;
  if (!/^[a-z0-9][a-z0-9_-]{0,47}$/.test(id.value)) {
    error.value = "The name needs lowercase letters, digits, - or _, up to 48 characters.";
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
    <p v-if="loadError" class="admin-panel-text error" role="alert">{{ loadError }} <button type="button" class="chip" @click="load">Retry</button></p>
    <p v-else-if="loading && !list" class="admin-panel-text muted" role="status">Loading…</p>
    <p v-else-if="list && !rows.length" class="admin-panel-text muted" :data-test="`empty-${kind}`">
      {{ list.gateways.length ? "No gateways match your search." : "No gateway is saved yet. Use + to add one." }}
      <button v-if="search" type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button>
    </p>
    <div v-else-if="list" class="admin-table-scroll" tabindex="0" role="region" :aria-labelledby="`${kind}-gateways-title`">
      <table class="admin-records">
        <thead><tr><th scope="col">Name</th><th scope="col">{{ chat ? "Provider and model" : "Kind and address" }}</th><th scope="col">Test</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <th scope="row">
              <div class="admin-record-name">
                <span class="admin-record-badge" aria-hidden="true">{{ row.id.slice(0, 2).toUpperCase() }}</span>
                <div>
                  <button type="button" class="admin-row-button" aria-haspopup="dialog" @click="show(row)">{{ row.id }}</button>
                  <p v-if="row.label">{{ row.label }}</p>
                </div>
              </div>
            </th>
            <td><code>{{ summary(row) || "—" }}</code><p class="kind">{{ row.provider ?? row.kind }}</p></td>
            <td><ConnectionTest :label="row.id" :run="() => agentsAdminClient.testModelGateway(kind, row.id)" /></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
  <Teleport to="body">
    <RecordDrawer ref="drawer" :open="open" :title="drawerTitle" editable :editing="editing" :busy="saving" :fallback-focus="() => searchField?.focus()"
      @edit="edit" @close="close" @discard="discard" @save="save">
      <form v-if="editing" :id="`${kind}-editor`" class="admin-editor" @submit.prevent="submit">
        <template v-if="creating && presets.length">
          <label :for="`${kind}-preset`">Start from</label>
          <select :id="`${kind}-preset`" v-model="preset" data-test="preset" :disabled="saving" @change="startFrom">
            <option value="">Nothing</option>
            <option v-for="item in presets" :key="item.key" :value="item.key">{{ item.label }}</option>
          </select>
        </template>
        <label :for="`${kind}-id`">Name</label>
        <input :id="`${kind}-id`" v-model="id" maxlength="48" autocomplete="off" spellcheck="false" required data-test="id" :disabled="saving || !creating" />
        <label :for="`${kind}-type`">{{ chat ? "Provider" : "Kind" }}</label>
        <select :id="`${kind}-type`" v-model="type" data-test="type" :disabled="saving || !creating" @change="fill({ [typeKey]: type })">
          <option v-for="name in types" :key="name" :value="name">{{ name }}</option>
        </select>
        <template v-if="chat && variants.length">
          <label :for="`${kind}-auth`">Sign-in</label>
          <select :id="`${kind}-auth`" v-model="auth" data-test="auth" :disabled="saving">
            <option v-for="name in variants" :key="name" :value="name">{{ name }}</option>
          </select>
        </template>
        <template v-if="needsModel">
          <label :for="`${kind}-model`">Model</label>
          <input :id="`${kind}-model`" v-model="model" maxlength="200" autocomplete="off" spellcheck="false" data-test="model" :disabled="saving" />
        </template>
        <fieldset v-if="needsModel" class="tiers">
          <legend>Model for each tier</legend>
          <p class="muted">Optional. The orchestrator picks the lightest tier whose description fits a task, and every agent that delegates reads these descriptions. An empty model uses the one above; an empty description keeps the default.</p>
          <div v-for="tier in TIERS" :key="tier" class="tier">
            <label :for="`${kind}-tier-${tier}`">{{ tier[0]?.toUpperCase() }}{{ tier.slice(1) }} model</label>
            <input :id="`${kind}-tier-${tier}`" v-model="tiers[tier]" maxlength="200" autocomplete="off" spellcheck="false" :data-test="`tier-${tier}`" :disabled="saving" />
            <label :for="`${kind}-note-${tier}`">When to use {{ tier }}</label>
            <input :id="`${kind}-note-${tier}`" v-model="notes[tier]" maxlength="300" autocomplete="off" :data-test="`note-${tier}`" :disabled="saving" placeholder="Default description" />
          </div>
        </fieldset>
        <template v-if="chat && type === 'openai'">
          <label :for="`${kind}-api`">API style</label>
          <select :id="`${kind}-api`" v-model="api" :disabled="saving">
            <option v-for="name in list?.form?.choices.api ?? []" :key="name" :value="name">{{ name }}</option>
          </select>
        </template>
        <template v-for="[name, label, secret, required] in fields" :key="name">
          <PasswordInput v-if="secret" v-model="secrets[name]" :label="label" autocomplete="off" :data-test="name" :disabled="saving"
            :placeholder="hasSecret(name) ? 'Leave empty to keep the saved value' : 'Paste it here; it is kept in Legion’s database and never shown again'" />
          <template v-else>
            <label :for="`${kind}-${name}`">{{ label }}</label>
            <input :id="`${kind}-${name}`" v-model="values[name]" autocomplete="off" spellcheck="false" :required="required" :data-test="name" :disabled="saving" />
          </template>
        </template>
        <label :for="`${kind}-timeout`">Time allowed (seconds)</label>
        <input :id="`${kind}-timeout`" v-model.number="timeout" type="number" min="0" max="1800" :disabled="saving" />
        <p v-if="error" class="error" role="alert" data-test="error">{{ error }}</p>
      </form>
      <div v-else-if="open && selected" class="admin-details">
        <dl>
          <dt>{{ chat ? "Provider" : "Kind" }}</dt><dd>{{ selected.provider ?? selected.kind }}</dd>
          <template v-if="summary(selected)"><dt>{{ selected.model ? "Model" : "Address" }}</dt><dd><code>{{ summary(selected) }}</code></dd></template>
          <dt>Reachable</dt><dd>{{ selected.reachable === undefined ? "Not checked" : selected.reachable ? "Yes" : "No" }}</dd>
        </dl>
        <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
        <section class="danger-zone">
          <h4>Danger zone</h4>
          <button type="button" class="danger" data-test="remove" @click="removing = true">Delete this gateway</button>
        </section>
      </div>
      <template v-if="editing" #footer>
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
.tiers { display: grid; gap: 6px; margin: 0; padding: 0; border: 0; min-width: 0; }
.tiers legend { padding: 0; margin-bottom: 4px; font-weight: 600; }
.tiers p { margin: 0 0 4px; font-size: 0.85rem; }
.tier { display: grid; gap: 6px; padding-top: 8px; border-top: 1px solid var(--border); }
.kind { margin: 2px 0 0; font-size: 0.8rem; color: var(--muted); }
</style>
