<script setup lang="ts">
import { ref } from "vue";
import type { ConnectionTestResult } from "../api/AgentsAdminClient";
import { errorMessage } from "../utils/errors";

/** A row's Test icon and its answer. The test only reads: it changes nothing and shows no token. */
const props = defineProps<{ label: string; run: () => Promise<ConnectionTestResult> }>();
const testing = ref(false);
const result = ref<ConnectionTestResult | null>(null);
const failure = ref("");

async function test() {
  if (testing.value) return;
  testing.value = true;
  result.value = null;
  failure.value = "";
  try {
    result.value = await props.run();
  } catch (err) {
    failure.value = errorMessage(err);
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <div class="connection-test">
    <button type="button" class="admin-icon" data-test="test" :aria-label="`Test ${label}`" :title="`Test ${label}`" :disabled="testing" :aria-busy="testing" @click="test">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h3l2-6 4 12 2-6h3" /></svg>
    </button>
    <p v-if="testing" class="muted" role="status">Testing…</p>
    <p v-else-if="failure" class="error" role="alert" data-test="test-failure">{{ failure }}</p>
    <div v-else-if="result" role="status" data-test="test-result">
      <p :class="result.ok ? 'ok' : 'error'"><span aria-hidden="true">{{ result.ok ? "✓" : "✕" }}</span> {{ result.message }}</p>
      <ul v-if="(result.origins?.length ?? 0) > 1" class="origins">
        <li v-for="(origin, index) in result.origins" :key="index" :class="origin.ok ? 'ok' : 'error'"><span aria-hidden="true">{{ origin.ok ? "✓" : "✕" }}</span> Address {{ index + 1 }}: {{ origin.message }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.connection-test { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.connection-test p, .origins { margin: 0; font-size: 0.85rem; }
.origins { padding: 0; list-style: none; }
.ok { color: var(--success); }
</style>
