<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import "../../components/layout/infoPage.css";
import PageLayout from "../../components/layout/PageLayout.vue";
import CopyButton from "../../components/ui/buttons/CopyButton.vue";
import ConfirmModal from "../../components/ui/dialogs/ConfirmModal.vue";
import PanelHelp from "../../components/ui/panel/PanelHelp.vue";
import SegmentedControl from "../../components/ui/forms/SegmentedControl.vue";
import StateMessage from "../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../stores/auth";
import { errorMessage } from "../../utils/errors";
import { formatBytes } from "../../utils/format";
import { publicOrigin } from "../../utils/server";
import { parseServerTime } from "../../utils/time";
import { FOLDER_MAX_MINUTES, foldersClient, type Folder, type FolderFile } from "./api/FoldersClient";
import FolderFiles from "./components/FolderFiles.vue";
import { timeLeft } from "./timeLeft";

/** The account's temporary folders: open one, copy its link, and anyone with the link can add and download files.
 * Only the owner removes files or ends the folder early. A folder is deleted at its set time whatever happens in it. */
const MAX_FILE_BYTES = 100 * 1024 * 1024; // the server's cap, shown before the first read
const LENGTHS = [
  { value: "5", label: "5 min" }, { value: "15", label: "15 min" },
  { value: "30", label: "30 min" }, { value: String(FOLDER_MAX_MINUTES), label: "1 hour" },
];

const auth = useAuthStore();
const folders = ref<Folder[]>([]);
const loading = ref(true);
const error = ref("");
const actionError = ref("");
const name = ref("");
const length = ref(String(FOLDER_MAX_MINUTES));
const busy = ref(false);
const now = ref(Date.now());
const ending = ref<Folder | null>(null);
const removing = ref<{ folder: Folder; file: FolderFile } | null>(null);
let ticker: ReturnType<typeof setInterval> | undefined;
let run = 0;

const linkOf = (folder: Folder): string => `${publicOrigin()}/folder/${folder.token}`;
const left = (folder: Folder): string => timeLeft(parseServerTime(folder.expires_at), now.value).replace(" left", "");
// A folder that just ran out leaves the list at once, before the next reload.
const open = computed(() => folders.value.filter((folder) => parseServerTime(folder.expires_at) > now.value));

async function load(): Promise<void> {
  const current = ++run;
  try {
    const list = await foldersClient.list();
    if (current !== run) return;
    folders.value = list;
    error.value = "";
  } catch (err) {
    if (current === run) error.value = errorMessage(err);
  } finally {
    if (current === run) loading.value = false;
  }
}

async function act(action: () => Promise<unknown>): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  actionError.value = "";
  try {
    await action();
    await load();
  } catch (err) {
    actionError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

const create = () => act(async () => {
  await foldersClient.create(name.value.trim(), Number(length.value));
  name.value = "";
});
const end = () => act(async () => { if (ending.value) await foldersClient.remove(ending.value.id); }).finally(() => { ending.value = null; });
const removeFile = () => act(async () => {
  if (removing.value) await foldersClient.removeFile(removing.value.folder.id, removing.value.file.id);
}).finally(() => { removing.value = null; });

onMounted(() => {
  void load();
  ticker = setInterval(() => { now.value = Date.now(); }, 1000);
});
onBeforeUnmount(() => { run++; clearInterval(ticker); });
watch(() => auth.account?.id, () => { folders.value = []; loading.value = true; void load(); });
</script>

<template>
  <PageLayout class="folders info-content" title="Temp folders">
    <template #actions>
      <PanelHelp title="Temporary folders">
        Create a folder and send its link to anyone: they need no account to download or add files. Each file can be {{ formatBytes(MAX_FILE_BYTES) }} at most.
        A folder is deleted when its time is up (an hour at most), and adding or removing files never changes that. Only you can remove files or delete the folder.
      </PanelHelp>
    </template>

    <form class="new" @submit.prevent="create">
      <input v-model="name" type="text" aria-label="Folder name" placeholder="Name a new folder" maxlength="60" autocomplete="off" required :disabled="busy" />
      <SegmentedControl v-model="length" :options="LENGTHS" aria-label="Delete after" />
      <button type="submit" class="pill-btn primary" :disabled="busy || name.trim() === ''">Create folder</button>
    </form>
    <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>

    <StateMessage v-if="loading" kind="loading">Loading …</StateMessage>
    <StateMessage v-else-if="error" kind="error" @retry="load">Could not load your folders: {{ error }}</StateMessage>
    <StateMessage v-else-if="!open.length" kind="empty">No folders yet. Name one above and choose how long it lasts, then press Create folder.</StateMessage>
    <template v-else>
      <section v-for="folder in open" :key="folder.id" class="card folder" :aria-label="folder.name">
        <header>
          <div>
            <h3>{{ folder.name }}</h3>
            <p class="muted">Deleted in {{ left(folder) }}</p>
          </div>
          <button type="button" class="pill-btn ghost" :disabled="busy" @click="ending = folder">Delete folder</button>
        </header>
        <div class="link">
          <input type="text" readonly :value="linkOf(folder)" :aria-label="`Link to ${folder.name}`" @focus="($event.target as HTMLInputElement).select()" />
          <CopyButton :text="linkOf(folder)" label="Copy link" />
        </div>
        <FolderFiles :token="folder.token" :files="folder.files" :max-file-bytes="MAX_FILE_BYTES" removable
          @added="load" @remove="(file) => (removing = { folder, file })" />
      </section>
    </template>

    <ConfirmModal :open="ending !== null" title="Delete this folder?" message="Its link stops working now and every file in it is deleted."
      confirm-label="Delete" danger :busy="busy" @confirm="end" @close="ending = null" />
    <ConfirmModal :open="removing !== null" title="Remove this file?" :message="`${removing?.file.name ?? ''} is deleted for everyone.`"
      confirm-label="Remove" danger :busy="busy" @confirm="removeFile" @close="removing = null" />
  </PageLayout>
</template>

<style scoped>
.new { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.new input { flex: 1 1 200px; min-width: 0; }
.folder { display: flex; flex-direction: column; gap: 12px; }
.folder header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.folder h3 { overflow-wrap: anywhere; }
.muted { margin: 2px 0 0; color: var(--muted); font-size: .85em; }
.error { color: var(--danger); }
.link { display: flex; align-items: center; gap: 8px; }
.link input { flex: 1; min-width: 0; font-family: var(--mono); font-size: .85em; }
@media (max-width: 767px) {
  .new button, .folder header button { min-height: 44px; min-width: 44px; }
  .new input, .link input { min-height: 44px; font-size: max(1em, 16px); }
  .folder header { flex-direction: column; align-items: stretch; }
}
</style>
