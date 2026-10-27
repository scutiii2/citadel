<script setup lang="ts">
import type { UsageRecordRow } from "../api/UsageClient";
import { formatCost, parseServerTime } from "../../../utils/analytics/usageFormat";

/** One model call in the Usage page's Recent calls list: the agent (and who handed it
 * the question), provider and gateway chips, when and with which model, and its tokens. */
defineProps<{ record: UsageRecordRow; currency?: string }>();

/** A naive-UTC API time as the viewer's local date and time. */
const localTime = (value: string): string => new Date(parseServerTime(value)).toLocaleString();
const tokens = (n: number): string => n.toLocaleString();
</script>

<template>
  <li class="call">
    <div class="call-main">
      <div>
        <span class="call-agent">{{ record.agent_id ?? record.agent ?? "unknown" }}</span>
        <span v-if="record.delegated_by" class="muted"> ← {{ record.delegated_by }}</span>
        <span v-if="record.kind === 'summary'" class="call-chip">summary</span>
        <span v-if="record.provider_id" class="call-chip">{{ record.provider_id }}</span>
        <span v-if="record.gateway" class="call-chip">{{ record.gateway }}</span>
      </div>
      <div class="muted small">{{ localTime(record.started_at ?? record.created_at) }}<template v-if="record.model"> · {{ record.model }}</template></div>
    </div>
    <div class="call-tokens">
      <strong>{{ tokens(record.total_tokens) }}<template v-if="record.cost != null"> · {{ formatCost(record.cost, currency) }}</template></strong>
      <span v-if="record.input_tokens !== null && record.output_tokens !== null" class="muted small">
        {{ tokens(record.input_tokens) }} in / {{ tokens(record.output_tokens) }} out
      </span>
    </div>
  </li>
</template>

<style scoped>
.call {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-top: 1px solid var(--border);
  font-size: 0.9em;
}
.call:first-child {
  padding-top: 0;
  border-top: none;
}
.call-main {
  min-width: 0;
  overflow-wrap: anywhere;
}
.call-agent {
  font-weight: 500;
}
.small {
  margin: 2px 0 0;
  font-size: 0.8em;
}
.call-tokens {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  font-variant-numeric: tabular-nums;
}
.muted {
  color: var(--muted);
}
</style>
