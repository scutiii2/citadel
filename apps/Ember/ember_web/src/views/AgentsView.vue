<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { agentsClient, type AgentListing } from "../api/AgentsClient";
import AgentCard from "../components/AgentCard.vue";
import "../components/infoPage.css";
import { errorMessage } from "../utils/errors";

/** Every agent behind ember, running or not (ember_api's GET /api/agents).
 * Read-only: new chats always go to the entry agent, which hands work to the
 * others itself. Refreshed every 15 s while the page is open. */

const REFRESH_MS = 15_000;

const agents = ref<AgentListing[]>([]);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");

const summary = computed(() => {
  const count = (status: AgentListing["status"]) => agents.value.filter((a) => a.status === status).length;
  const parts = [`${count("running")} running`];
  if (count("offline")) parts.push(`${count("offline")} offline`);
  if (count("disabled")) parts.push(`${count("disabled")} disabled`);
  return parts.join(" · ");
});

async function refresh(): Promise<void> {
  refreshing.value = true;
  try {
    agents.value = await agentsClient.list();
    error.value = "";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

let timer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  void refresh();
  timer = setInterval(() => void refresh(), REFRESH_MS);
});
onUnmounted(() => {
  if (timer !== null) clearInterval(timer);
});
</script>

<template>
  <PageLayout class="info-content" title="Agents" description="The AI agents behind ember. New chats go to the entry agent, which hands work to the others.">
    <template #actions>
      <button type="button" class="chip" :disabled="refreshing" @click="refresh">Refresh</button>
    </template>
    <div class="column">
      <p v-if="error" class="error">Could not load the agents: {{ error }}</p>
      <p v-if="loading" class="muted">Loading …</p>
      <p v-else-if="agents.length === 0 && !error" class="muted">No agents are running or defined.</p>
      <template v-else-if="agents.length">
        <p class="muted summary">{{ summary }}</p>
        <div class="grid">
          <AgentCard v-for="agent in agents" :key="agent.id" :agent="agent" />
        </div>
      </template>
    </div>
  </PageLayout>
</template>

<style scoped>
.summary {
  margin: 0 0 10px;
  font-size: 0.9em;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  grid-auto-rows: 1fr;
  gap: 12px;
}
</style>
