<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { isApiStatus } from "../../api/http";
import { errorMessage } from "../../utils/errors";
import { parseServerTime } from "../../utils/time";
import { foldersClient, type PublicFolder } from "./api/FoldersClient";
import FolderFiles from "./components/FolderFiles.vue";
import { timeLeft } from "./timeLeft";

/** A folder someone shared by link. Open to anyone (no login): download and add files, never remove. */
const route = useRoute();
const token = computed(() => String(route.params.token ?? ""));
const folder = ref<PublicFolder | null>(null);
const loading = ref(true);
// "gone": unknown, deleted or expired - the server does not say which.
const problem = ref<"gone" | "busy" | "error" | null>(null);
const problemText = ref("");
const now = ref(Date.now());
const originalTitle = document.title;
let ticker: ReturnType<typeof setInterval> | undefined;

async function load(): Promise<void> {
  const requested = token.value;
  problem.value = null;
  try {
    const view = await foldersClient.read(requested);
    if (requested !== token.value) return;
    folder.value = view;
    document.title = `${view.name} - Ember`;
  } catch (err) {
    if (requested !== token.value) return;
    folder.value = null;
    if (isApiStatus(err, 404)) problem.value = "gone";
    else if (isApiStatus(err, 429)) problem.value = "busy";
    else {
      problem.value = "error";
      problemText.value = errorMessage(err);
    }
  } finally {
    if (requested === token.value) loading.value = false;
  }
}

const expired = computed(() => folder.value !== null && parseServerTime(folder.value.expires_at) <= now.value);
watch(token, () => { loading.value = true; void load(); }, { immediate: true });
onMounted(() => { ticker = setInterval(() => { now.value = Date.now(); }, 1000); });
onBeforeUnmount(() => { clearInterval(ticker); document.title = originalTitle; });
</script>

<template>
  <section class="shared">
    <div class="column page-column">
      <p v-if="loading" class="status">Loading …</p>
      <div v-else-if="problem === 'gone' || expired" class="status" role="alert">
        <h2 class="page-title">This link does not work</h2>
        <p>It never existed, or the folder was deleted, or its time ran out. Ask whoever sent it for a new one.</p>
      </div>
      <div v-else-if="problem === 'busy'" class="status" role="alert">
        <h2 class="page-title">Too many requests</h2>
        <p>Wait a minute and reload this page.</p>
        <button type="button" @click="load">Try again</button>
      </div>
      <div v-else-if="problem === 'error'" class="status" role="alert">
        <h2 class="page-title">Could not load this folder</h2>
        <p>{{ problemText }}</p>
        <button type="button" @click="load">Try again</button>
      </div>
      <template v-else-if="folder">
        <header>
          <h2 class="page-title">{{ folder.name }}</h2>
          <p class="note page-description">A temporary folder, deleted in {{ timeLeft(parseServerTime(folder.expires_at), now).replace(" left", "") }}.</p>
        </header>
        <FolderFiles :token="token" :files="folder.files" :max-file-bytes="folder.max_file_bytes" @added="load" />
      </template>
    </div>
  </section>
</template>

<style scoped>
.shared { flex: 1; min-height: 0; overflow-y: auto; scrollbar-gutter: stable; }
.column { display: flex; flex-direction: column; gap: 18px; }
header h2 { overflow-wrap: anywhere; }
.note { margin: 0; color: var(--muted); }
.status { margin-top: 15vh; text-align: center; color: var(--muted); }
.status h2 { color: var(--text); }
.status button { padding: 5px 16px; border: 1px solid var(--border); border-radius: var(--radius-full); cursor: pointer; color: var(--text); background: transparent; }
</style>
