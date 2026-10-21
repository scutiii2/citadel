<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import PageLayout from "../components/PageLayout.vue";
import MarkdownContent from "../components/MarkdownContent.vue";
import { brainsClient, type BrainResult, type BrainScope } from "../api/BrainsClient";
import { errorMessage } from "../utils/errors";
const route = useRoute();
const scope = ref<BrainScope | "both">(route.query.scope === "personal" ? "personal" : "instance");
const path = ref(typeof route.query.path === "string" ? route.query.path : "");
const query = ref("");
const result = ref<BrainResult | null>(null);
const busy = ref(false);
const error = ref("");
async function run(operation: "list" | "read" | "search" | "status", nextPath = path.value) {
  if (busy.value) return;
  busy.value = true; error.value = ""; result.value = null;
  try { result.value = await brainsClient.browse(scope.value, operation, nextPath, query.value); path.value = nextPath; }
  catch (e) { error.value = errorMessage(e); }
  finally { busy.value = false; }
}
onMounted(() => { if (path.value) void run("read"); });
</script>
<template>
  <PageLayout title="Brains" description="Durable knowledge from the shared Instance Brain and your Personal Brain.">
    <div class="brain-column" :aria-busy="busy">
      <p>All signed-in users can read the Instance Brain. Personal Brain contents remain scoped to your account. Configure your connection in Settings.</p>
      <fieldset :disabled="busy">
        <label>Destination<select v-model="scope"><option value="instance">Instance Brain</option><option value="personal">Personal Brain</option><option value="both">Both brains</option></select></label>
        <label>Search<input v-model="query" @keyup.enter="run('search')" /></label>
        <button type="button" @click="run('search')">Search brains</button>
        <label>Vault-relative path<input v-model="path" placeholder="Inbox/Example.md" /></label>
        <div class="actions"><button type="button" :disabled="scope === 'both'" @click="run('list')">Browse folder</button><button type="button" :disabled="scope === 'both'" @click="run('read')">Read document</button><button type="button" :disabled="scope === 'both'" @click="run('status')">Check connection</button></div>
      </fieldset>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <p v-if="result?.message" role="status">{{ result.message }}</p>
      <p v-if="result?.refreshing">Indexing is in progress. Results use completed documents.</p>
      <p v-for="failure in result?.failures" :key="failure.scope" role="status">{{ failure.scope }}: {{ failure.message }}</p>
      <ul v-if="result?.entries"><li v-for="entry in result.entries" :key="entry.path"><button type="button" :disabled="busy" @click="run(entry.kind === 'folder' ? 'list' : 'read', entry.path)">{{ entry.path }}</button></li></ul>
      <MarkdownContent v-if="result?.content" :text="result.content" />
      <article v-for="hit in result?.hits" :key="`${hit.scope}:${hit.path}:${hit.heading}`">
        <h3>{{ hit.connection_label }} · {{ hit.path }} · {{ hit.heading }}</h3><p>{{ hit.scope }} · {{ hit.refresh_status }}</p><MarkdownContent :text="hit.content" />
      </article>
    </div>
  </PageLayout>
</template>
<style scoped>
.brain-column { width: 100%; max-width: 820px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
fieldset { display: grid; gap: 12px; border: 0; padding: 0; }
label { display: grid; gap: 4px; }
input, select { padding: 8px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); min-width: 0; }
button { color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-full); padding: 7px 12px; cursor: pointer; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
article { border-top: 1px solid var(--border); margin-top: 16px; overflow-wrap: anywhere; }
.error { color: var(--danger); }
</style>
