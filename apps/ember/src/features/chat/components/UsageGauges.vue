<script setup lang="ts">
import { onMounted, watch } from "vue";
import { resetText, useUsageLimitsStore, type LimitWindow } from "../../usage/stores/usageLimits";
import { compactNumber } from "../../../utils/analytics/usageFormat";

// The 6-hour and weekly token limits, small, so they stay in view while
// chatting. Only windows that have a limit are shown. Refreshed when an answer
// ends (`busy` goes false), which also moves the header's ring.
const props = defineProps<{ busy: boolean }>();

const store = useUsageLimitsStore();

function hint(g: LimitWindow): string {
  const used = `${g.window.used.toLocaleString()} of ${g.window.limit.toLocaleString()} tokens`;
  return [`${g.title}: ${used}.`, resetText(g)].filter(Boolean).join(" ");
}

onMounted(() => void store.load());
watch(
  () => props.busy,
  (busy) => {
    if (!busy) void store.load();
  },
);
</script>

<template>
  <div v-if="store.windows.length" class="gauges" aria-label="Token limits">
    <div v-for="g in store.windows" :key="g.key" class="gauge" :title="hint(g)">
      <div class="head">
        <span>{{ g.key }}</span>
        <span>{{ compactNumber(g.window.used) }} / {{ compactNumber(g.window.limit) }}</span>
      </div>
      <div
        class="bar"
        role="progressbar"
        :aria-label="g.title"
        :aria-valuenow="g.percent"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :class="{ full: g.percent >= 90 }" :style="{ width: `${g.percent}%` }" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.gauges {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 3px;
  font-size: 0.75em;
  color: var(--muted);
}
.bar {
  height: 5px;
  border-radius: var(--radius-full);
  overflow: hidden;
  background: var(--code-bg);
}
.bar span {
  display: block;
  height: 100%;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.bar span.full {
  background: var(--danger);
}
</style>
