<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { ConnectionTestResult, GatewaySettingsPatch, GatewaySettingsView } from "../api/AgentsAdminClient";
import ConnectionTest from "./ConnectionTest.vue";
import PasswordInput from "./PasswordInput.vue";
import RecordDrawer from "./admin/RecordDrawer.vue";
import { errorMessage } from "../utils/errors";

const props = defineProps<{
  id: string;
  title: string;
  example: string;
  search: string;
  fallbackFocus?: () => void;
  load: () => Promise<GatewaySettingsView>;
  store: (changes: GatewaySettingsPatch) => Promise<GatewaySettingsView>;
  test: () => Promise<ConnectionTestResult>;
}>();
const emit = defineEmits<{ visible: [visible: boolean] }>();
const saved = ref<GatewaySettingsView>();
const url = ref("");
const description = ref("");
const token = ref("");
const clearToken = ref(false);
const loading = ref(false);
const loadError = ref("");
const saving = ref(false);
const error = ref("");
const notice = ref("");
const open = ref(false);
const editing = ref(false);
const drawer = ref<InstanceType<typeof RecordDrawer>>();

const visible = computed(() => !saved.value || [props.title, saved.value.description, saved.value.url]
  .some((value) => value?.toLowerCase().includes(props.search.trim().toLowerCase())));
watch(visible, (value) => emit("visible", value), { immediate: true });
const changes = computed<GatewaySettingsPatch>(() => ({
  ...(url.value.trim() !== saved.value?.url ? { url: url.value.trim() } : {}),
  ...(description.value.trim() !== (saved.value?.description ?? "") ? { description: description.value.trim() } : {}),
  ...(clearToken.value || token.value ? { token: clearToken.value ? "" : token.value } : {}),
}));

async function load() {
  if (loading.value) return;
  loading.value = true;
  loadError.value = "";
  try {
    saved.value = await props.load();
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function edit() {
  if (!saved.value) return;
  url.value = saved.value.url;
  description.value = saved.value.description ?? "";
  token.value = "";
  clearToken.value = false;
  error.value = notice.value = "";
  editing.value = true;
}

function discard() {
  editing.value = false;
  token.value = "";
  clearToken.value = false;
}

function close() {
  discard();
  open.value = false;
}

function submit() {
  if (!Object.keys(changes.value).length || saving.value) return;
  error.value = "";
  try {
    const parsed = new URL(url.value.trim());
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password ||
      parsed.search || parsed.hash || url.value.trim().length > 300) throw new Error();
  } catch {
    error.value = "Enter an HTTP(S) address without credentials, query, or fragment.";
    return;
  }
  drawer.value?.requestSave();
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    saved.value = await props.store(changes.value);
    notice.value = "Saved. Agents use the new values within half a minute.";
    discard();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <tr v-show="visible">
    <th scope="row">
      <div class="admin-record-name">
        <span class="admin-record-badge" aria-hidden="true">{{ title.slice(0, 2).toUpperCase() }}</span>
        <div>
          <button v-if="saved" type="button" class="admin-row-button" aria-haspopup="dialog" @click="open = true">{{ title }}</button>
          <span v-else>{{ title }}</span>
          <p v-if="saved?.description">{{ saved.description }}</p>
        </div>
      </div>
    </th>
    <td>
      <code v-if="saved">{{ saved.url }}</code>
      <span v-else-if="loading" class="muted" role="status">Loading…</span>
      <template v-else-if="loadError">
        <span class="error" role="alert">{{ loadError }}</span>
        <button class="chip" type="button" @click="load">Retry</button>
      </template>
    </td>
    <td><ConnectionTest v-if="saved" :label="title" :run="test" /></td>
  </tr>
  <Teleport to="body">
    <RecordDrawer ref="drawer" :open="open" :title="title" editable :editing="editing" :busy="saving" :fallback-focus="fallbackFocus"
      @edit="edit" @close="close" @discard="discard" @save="save">
      <form v-if="editing" :id="`${id}-editor`" class="admin-editor" @submit.prevent="submit">
        <label :for="`${id}-description`">Description</label>
        <textarea :id="`${id}-description`" v-model="description" maxlength="500" rows="3" :disabled="saving" data-test="description" />
        <label :for="`${id}-url`">Connection URL</label>
        <input :id="`${id}-url`" v-model="url" type="url" inputmode="url" maxlength="300" autocomplete="off" spellcheck="false"
          required data-test="url" :disabled="saving" :aria-describedby="`${id}-url-help`" />
        <p :id="`${id}-url-help`" class="muted">For example {{ example }} inside Docker.</p>
        <PasswordInput v-model="token" label="Access token" autocomplete="off" data-test="token" :disabled="saving || clearToken"
          :placeholder="saved?.has_token ? 'Leave empty to keep the saved token' : 'Paste the token made for Legion'" />
        <button v-if="saved?.has_token" type="button" class="chip" data-test="clear-token" :disabled="saving" :aria-pressed="clearToken" @click="clearToken = !clearToken">
          {{ clearToken ? 'Keep saved token' : 'Remove token' }}
        </button>
        <p v-if="clearToken" role="status">The saved token will be removed when you save.</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </form>
      <div v-else-if="open && saved" class="admin-details">
        <p v-if="saved.description">{{ saved.description }}</p>
        <dl>
          <dt>Connection URL</dt><dd><code>{{ saved.url }}</code></dd>
          <dt>Access token</dt><dd data-test="token-state">{{ saved.has_token ? 'A token is saved.' : 'No token is saved yet.' }}</dd>
        </dl>
        <p class="muted">Manage tokens on the gateway’s admin page under Access tokens.</p>
        <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      </div>
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="saving" data-test="cancel-edit" @click="drawer?.requestCancel()">Cancel</button>
        <button type="submit" :form="`${id}-editor`" class="primary" data-test="save" :disabled="saving || !Object.keys(changes).length" :aria-busy="saving">Save changes</button>
      </template>
    </RecordDrawer>
  </Teleport>
</template>
