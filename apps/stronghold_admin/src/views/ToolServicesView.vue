<script setup lang="ts">
import { onMounted, ref } from "vue";
import { toolServicesClient, type ToolSaveBody, type ToolService, type ToolTestResult } from "../api/ToolServicesClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PageLayout from "../components/PageLayout.vue";
import PasswordInput from "../components/PasswordInput.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

interface AddressRow {
  key: number;
  address: string;
  name: string;
  found: boolean | null;
  hasOverride: boolean;
  token: string;
  lookup: number;
  checking: boolean;
  error: string;
}

interface Draft {
  saved: ToolService;
  enabled: boolean;
  token: string;
  addresses: AddressRow[];
  pending: "save" | "test" | "clear" | null;
  error: string;
  notice: string;
  result: ToolTestResult | null;
}

let nextKey = 0;
const cards = ref<Draft[]>([]);
const loading = ref(true);
const loadError = ref("");
const removing = ref<Draft | null>(null);

function addressRow(): AddressRow {
  return { key: nextKey++, address: "", name: "", found: null, hasOverride: false,
    token: "", lookup: 0, checking: false, error: "" };
}

function apply(draft: Draft, saved: ToolService) {
  draft.saved = saved;
  draft.enabled = saved.enabled;
  draft.token = "";
  draft.addresses = saved.origins.length
    ? saved.origins.map((origin) => ({
        ...addressRow(), address: origin.origin ?? "", found: origin.origin ? true : null,
        hasOverride: origin.has_override, error: origin.origin ? "" : "This address left Treasury’s catalog.",
      }))
    : [addressRow()];
  draft.result = null;
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    cards.value = (await toolServicesClient.list()).map((saved) => {
      const draft: Draft = { saved, enabled: saved.enabled, token: "", addresses: [],
        pending: null, error: "", notice: "", result: null };
      apply(draft, saved);
      return draft;
    });
  } catch (error) {
    loadError.value = errorMessage(error);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function addressChanged(row: AddressRow) {
  row.lookup++;
  row.checking = false;
  row.found = null;
  row.name = row.token = row.error = "";
  row.hasOverride = false;
}

async function check(draft: Draft, row: AddressRow) {
  const address = row.address.trim();
  if (!address || row.checking || (row.found === true && row.name)) return;
  const lookup = ++row.lookup;
  const current = () => draft.addresses.includes(row) && row.lookup === lookup;
  row.checking = true;
  row.error = "";
  try {
    const result = await toolServicesClient.lookup(address);
    if (!current()) return;
    row.found = result.found;
    if (result.found && result.group) row.name = result.group.name;
  } catch (error) {
    if (current()) row.error = errorMessage(error);
  } finally {
    if (current()) row.checking = false;
  }
}

function hasAddresses(draft: Draft): boolean {
  return draft.saved.origins.length > 0 || draft.addresses.length > 1 || draft.addresses.some((row) => !!row.address.trim());
}

function canSave(draft: Draft): boolean {
  if (!hasAddresses(draft)) return draft.enabled !== draft.saved.enabled || !!draft.token;
  return draft.addresses.every((row) => !!row.address.trim() && !row.checking && !row.error
    && (row.found === true || (row.found === false && !!row.name.trim())));
}

async function save(draft: Draft) {
  if (draft.pending || !canSave(draft)) return;
  const body: ToolSaveBody = { enabled: draft.enabled };
  if (draft.token) body.token = draft.token;
  if (hasAddresses(draft)) {
    body.addresses = draft.addresses.map((row) => ({
      address: row.address.trim(),
      ...(row.found ? {} : { name: row.name.trim() }),
      ...(row.token ? { header_value: row.token } : {}),
    }));
  }
  await run(draft, "save", async () => {
    apply(draft, await toolServicesClient.save(draft.saved.name, body));
    draft.notice = "Connection saved.";
  });
}

async function run(draft: Draft, action: NonNullable<Draft["pending"]>, perform: () => Promise<void>) {
  if (draft.pending) return;
  draft.pending = action;
  draft.error = draft.notice = "";
  draft.result = null;
  try {
    await perform();
  } catch (error) {
    draft.error = errorMessage(error);
  } finally {
    draft.pending = null;
  }
}

async function test(draft: Draft) {
  await run(draft, "test", async () => { draft.result = await toolServicesClient.test(draft.saved.name); });
}

async function clear() {
  const draft = removing.value;
  if (!draft || draft.pending) return;
  await run(draft, "clear", async () => {
    apply(draft, await toolServicesClient.clear(draft.saved.name));
    draft.notice = "Connection removed.";
  });
  removing.value = null;
}

function resultAddress(draft: Draft, originId: string): string {
  return draft.saved.origins.find((origin) => origin.origin_id === originId)?.origin ?? "Unavailable address";
}
</script>

<template>
  <PageLayout
    class="info-content tool-services"
    title="Tool services"
    description="Citadel services call Bard, Scribe and Reader through these addresses. Treasury stores the addresses. Stronghold keeps the tokens and never displays them again. Add a backup address to keep working when the first one is down."
  >
    <p v-if="loading" class="muted" role="status">Loading…</p>
    <div v-else-if="loadError">
      <p class="error" role="alert">{{ loadError }}</p>
      <button class="chip" type="button" @click="load">Retry</button>
    </div>

    <div v-else class="cards">
      <form
        v-for="draft in cards"
        :key="draft.saved.name"
        class="card"
        :aria-labelledby="draft.saved.name + '-title'"
        :data-test="'service-' + draft.saved.name"
        @submit.prevent="save(draft)"
      >
        <header>
          <h2 :id="draft.saved.name + '-title'">{{ draft.saved.label }}</h2>
          <p class="state" :class="{ ready: draft.saved.ready }">
            <span aria-hidden="true">{{ draft.saved.ready ? "✓" : "○" }}</span>
            {{ draft.saved.ready ? "Ready" : draft.saved.reason ?? "Not ready" }}
          </p>
        </header>

        <ToggleSwitch
          :checked="draft.enabled"
          :disabled="!!draft.pending"
          @change="draft.enabled = ($event.target as HTMLInputElement).checked"
        >Enabled</ToggleSwitch>

        <PasswordInput
          v-model="draft.token"
          label="Connection token"
          autocomplete="new-password"
          :placeholder="draft.saved.has_token ? 'Leave empty to keep the saved token' : undefined"
          :disabled="!!draft.pending"
        />

        <fieldset v-for="(row, index) in draft.addresses" :key="row.key" class="address-row" :disabled="!!draft.pending">
          <legend>{{ index === 0 ? "Primary address" : "Backup address " + index }}</legend>
          <div class="field">
            <label :for="'address-' + row.key">Address</label>
            <input
              :id="'address-' + row.key"
              v-model="row.address"
              type="url"
              autocomplete="off"
              spellcheck="false"
              :data-test="'address-' + index"
              :aria-invalid="!!row.error"
              :aria-describedby="row.error ? 'address-error-' + row.key : undefined"
              @input="addressChanged(row)"
              @blur="check(draft, row)"
            />
            <p v-if="row.checking" class="help" role="status">Checking Treasury…</p>
            <p v-if="row.error" :id="'address-error-' + row.key" class="error" role="alert">{{ row.error }}</p>
          </div>
          <div v-if="row.found === false || row.name" class="field">
            <label :for="'service-name-' + row.key">Outside service name</label>
            <input
              :id="'service-name-' + row.key"
              v-model="row.name"
              :readonly="row.found === true"
              :required="row.found === false"
              autocomplete="off"
              spellcheck="false"
              :data-test="'name-' + index"
            />
          </div>
          <PasswordInput
            v-model="row.token"
            label="Address token (optional)"
            autocomplete="new-password"
            :placeholder="row.hasOverride ? 'Leave empty to keep the saved token' : undefined"
            :disabled="!!draft.pending"
          />
          <div v-if="draft.addresses.length > 1">
            <button class="chip" type="button" @click="draft.addresses.splice(index, 1)">Remove address</button>
          </div>
        </fieldset>

        <div>
          <button class="chip" type="button" data-test="add-address" :disabled="!!draft.pending" @click="draft.addresses.push(addressRow())">
            Add a backup address
          </button>
        </div>
        <p v-if="draft.error" class="error" role="alert">{{ draft.error }}</p>
        <p v-if="draft.notice" class="help" role="status">{{ draft.notice }}</p>
        <div v-if="draft.result" data-test="test-result" role="status">
          <p>{{ draft.result.message }}</p>
          <ul v-if="draft.result.origins.length">
            <li v-for="origin in draft.result.origins" :key="origin.origin_id">
              {{ resultAddress(draft, origin.origin_id) }} — {{ origin.message }}
            </li>
          </ul>
        </div>
        <div class="actions">
          <button
            class="chip" type="button" data-test="test" :disabled="!!draft.pending"
            :aria-busy="draft.pending === 'test'" @click="test(draft)"
          >{{ draft.pending === "test" ? "Testing…" : "Test" }}</button>
          <button
            class="primary" type="submit" data-test="save" :disabled="!!draft.pending || !canSave(draft)"
            :aria-busy="draft.pending === 'save'"
          >{{ draft.pending === "save" ? "Saving…" : "Save" }}</button>
        </div>
        <div v-if="draft.saved.origins.length || draft.saved.has_token || !draft.saved.enabled" class="remove">
          <button
            class="danger" type="button" data-test="clear" :disabled="!!draft.pending" @click="removing = draft"
          >Remove connection</button>
        </div>
      </form>
    </div>

    <ConfirmModal
      :open="removing !== null"
      :title="'Remove ' + (removing?.saved.label ?? '') + ' connection?'"
      message="This clears the saved addresses and tokens from Stronghold. The addresses stay in Treasury."
      confirm-label="Remove connection"
      danger
      :busy="removing?.pending === 'clear'"
      @close="removing = null"
      @confirm="clear"
    />
  </PageLayout>
</template>

<style scoped>
.cards { display: grid; gap: 16px; max-width: 720px; }
.card { display: grid; gap: 12px; min-width: 0; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.card h2 { margin: 0; font-size: 1em; font-weight: 600; }
.card p { margin: 0; overflow-wrap: anywhere; }
.state, .help { color: var(--muted); font-size: 0.9em; }
.state.ready { color: var(--success); }
.address-row { display: grid; gap: 8px; min-width: 0; margin: 0; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.address-row legend { padding: 0 4px; font-size: 0.9em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field label { font-size: 0.9em; font-weight: 600; }
.field input { min-width: 0; min-height: 44px; width: 100%; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.remove { padding-top: 12px; border-top: 1px solid var(--border); }
.card li { overflow-wrap: anywhere; }
</style>
