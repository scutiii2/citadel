<script setup lang="ts">
import { onMounted, ref } from "vue";
import { treasuryAdminClient, type TreasuryView } from "../api/TreasuryAdminClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

const view = ref<TreasuryView | null>(null);
const error = ref("");
const loading = ref(true);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    view.value = await treasuryAdminClient.get();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageLayout
    class="info-content instances"
    title="Instances"
    description="The databases Treasury serves. Each instance lists the connections it may use. They are set in Treasury's own configuration files, so this page only shows them."
  >
    <template #actions>
      <button type="button" :disabled="loading" @click="load">Refresh</button>
    </template>
    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
    <template v-else-if="view">
      <p v-if="!view.reachable" class="error" role="alert">Treasury does not answer. Check that it is running.</p>
      <ul v-else class="cards" aria-label="Instances">
        <li v-for="instance in view.instances" :key="instance.name" class="card">
          <h2 class="title">{{ instance.name }}</h2>
          <p class="muted">
            <template v-if="instance.connections.length">Connections: {{ instance.connections.join(", ") }}</template>
            <template v-else>No connections</template>
          </p>
          <p v-if="instance.name === view.portcullis.instance" class="muted" data-test="portcullis">
            Portcullis stores its data here, in connection "{{ view.portcullis.connection }}".
          </p>
        </li>
      </ul>
    </template>
  </PageLayout>
</template>

<style scoped>
.cards { display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; }
.card { display: grid; gap: 6px; max-width: 560px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.muted { margin: 0; color: var(--muted); }
.error { margin: 0; color: var(--danger); }
</style>
