<script setup lang="ts">
import { computed, ref } from "vue";
import type { MyUsage, UsageGroupBy, UsageRecordRow } from "../../api/UsageClient";
import SegmentedControl from "../SegmentedControl.vue";
import LineChart from "../analytics/LineChart.vue";
import UsageHeatmap from "../UsageHeatmap.vue";
import UsageCall from "./UsageCall.vue";
import { formatUtc } from "../../utils/errors";
import { parseServerTime, usagePercent as percent } from "../../utils/usageFormat";
import { favoriteAgent, hourLabel, peakHour, utcDay } from "../../utils/usageStats";
const props = defineProps<{ username: string; usage: MyUsage; year: MyUsage | null; records: UsageRecordRow[]; recordsFailed: boolean; yearFailed: boolean; loading: boolean; groupBy: UsageGroupBy }>();
const emit = defineEmits<{ group: [value: UsageGroupBy] }>();
const groupBy = computed({ get: () => props.groupBy, set: value => emit("group", value) });
const today = utcDay(new Date());
const GROUP_OPTIONS: { value: UsageGroupBy; label: string }[] = [{ value: "agent", label: "Agent" }, { value: "model", label: "Model" }, { value: "provider", label: "Provider" }, { value: "gateway", label: "Gateway" }];
const groupHeading = computed(() => GROUP_OPTIONS.find(o => o.value === props.usage.report.group_by)?.label ?? "Agent");
const groupTotal = computed(() => Math.max(1, props.usage.report.groups.reduce((sum, g) => sum + g.tokens, 0)));
function tokens(n: number): string { return n.toLocaleString(); }
function localTime(value: string): string { return new Date(parseServerTime(value)).toLocaleString(); }

/** The calls of one response (they share a turn_id), newest response first. */
interface Turn {
  id: string;
  /** The agent that took the question: the call nothing delegated, else the earliest. */
  lead: string;
  rows: UsageRecordRow[];
  total: number;
  /** When the response's first call began. */
  at: string;
}
const startOf = (r: UsageRecordRow): string => r.started_at ?? r.created_at;
const agentName = (r: UsageRecordRow): string => r.agent_id ?? r.agent ?? "unknown";
const turns = computed<Turn[]>(() => {
  const byTurn = new Map<string, UsageRecordRow[]>();
  for (const r of props.records) {
    const list = byTurn.get(r.turn_id);
    if (list) list.push(r);
    else byTurn.set(r.turn_id, [r]);
  }
  return [...byTurn].map(([id, rows]) => {
    // The orchestrator first, then the specialists in the order they ran.
    const ordered = [...rows].sort(
      (a, b) => Number(a.delegated_by !== null) - Number(b.delegated_by !== null) || startOf(a).localeCompare(startOf(b)),
    );
    return {
      id,
      lead: agentName(ordered[0]!),
      rows: ordered,
      total: ordered.reduce((sum, r) => sum + r.total_tokens, 0),
      at: ordered.map(startOf).sort()[0]!,
    };
  });
});
const openTurns = ref<Set<string>>(new Set());
function toggleTurn(id: string): void {
  const next = new Set(openTurns.value);
  if (!next.delete(id)) next.add(id);
  openTurns.value = next;
}
const peak = computed(() => peakHour(props.usage.report.hourly));
const favorite = computed(() => favoriteAgent(props.usage.report.by_agent));
const activitySeries = computed(() => {
  const report = props.usage.report;
  if (report.daily.length === 0) return [];
  const daily = new Map(report.daily.map(day => [day.date, day.tokens]));
  const first = new Date(report.since.slice(0, 10) + "T00:00:00Z").getTime();
  const last = new Date(today + "T00:00:00Z").getTime();
  const series: { bucket: string; values: { tokens: number } }[] = [];
  for (let day = first; day <= last; day += 86_400_000) {
    const date = new Date(day).toISOString().slice(0, 10);
    series.push({ bucket: date + "T00:00:00", values: { tokens: daily.get(date) ?? 0 } });
  }
  return series;
});
const ACTIVITY_LINES = [{ id: "tokens", label: "Tokens", color: "var(--accent)" }];
</script>

<template>
<section class="usage-details" :aria-label="`Usage for ${username}`">
<h3>Usage for {{ username }}</h3>
<p v-if="yearFailed" class="muted">Could not load annual activity.</p>

        <div class="panel limits">
          <div class="panel-head"><h3>Limits</h3><span class="muted small">Rolling windows</span></div>
          <div class="limit-grid">
            <div v-for="w in [{ key: '6 hours', v: usage.six_hour }, { key: '7 days', v: usage.weekly }]" :key="w.key">
              <div class="limit-head">
                <span>Last {{ w.key }}</span>
                <span class="muted">
                  {{ tokens(w.v.used) }}<template v-if="w.v.limit"> / {{ tokens(w.v.limit) }}</template> tokens
                </span>
              </div>
              <div v-if="w.v.limit" class="bar" role="progressbar" :aria-valuenow="percent(w.v)" aria-valuemin="0" aria-valuemax="100">
                <span :class="{ full: percent(w.v) >= 90 }" :style="{ width: `${percent(w.v)}%` }" />
              </div>
              <p v-else class="muted small">No limit.</p>
              <p v-if="w.v.reset_at && w.v.used" class="muted small">
                Oldest tokens stop counting at {{ formatUtc(w.v.reset_at) }}.
              </p>
            </div>
          </div>
        </div>

        <div class="stats">
          <div class="stat"><strong>{{ tokens(usage.report.total_tokens) }}</strong><span>tokens</span></div>
          <div class="stat"><strong>{{ tokens(usage.report.turns) }}</strong><span>answers</span></div>
          <div class="stat"><strong>{{ tokens(usage.report.chats) }}</strong><span>chats</span></div>
        </div>

        <div class="panel activity">
          <div class="panel-head"><h3>Activity</h3><span class="muted small">Per day, UTC</span></div>
          <p v-if="usage.report.daily.length === 0" class="muted">No usage in this period.</p>
          <LineChart v-else :series="activitySeries" :lines="ACTIVITY_LINES" bucket="day" label="Token usage" fill :loading="loading" />

          <template v-if="year">
            <h4>Last 12 months</h4>
            <UsageHeatmap v-if="year.report.daily.length" :daily="year.report.daily" :today="today" />
            <p v-else class="muted">No usage in the last 12 months.</p>
            <p class="muted small">Days are UTC days.</p>
          </template>

          <p v-if="peak !== null || favorite" class="insights">
            <span v-if="peak !== null" class="insight">Busiest hour (your time) <strong>{{ hourLabel(peak) }}</strong></span>
            <span v-if="favorite" class="insight">Favorite agent <strong>{{ favorite }}</strong></span>
            <span class="insight">Active days <strong>{{ usage.report.daily.length }}</strong></span>
          </p>
        </div>

        <div class="panel breakdown">
          <div class="panel-head">
            <h3>Breakdown</h3>
            <SegmentedControl v-model="groupBy" :options="GROUP_OPTIONS" label="Group by" aria-label="Group usage by" />
          </div>
          <p v-if="usage.report.groups.length === 0" class="muted">None.</p>
          <table v-else class="groups">
            <thead>
              <tr><th>{{ groupHeading }}</th><th>Share</th><th class="num">Tokens</th><th class="num">Turns</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in usage.report.groups" :key="g.key">
                <td>{{ g.key }}</td>
                <td class="share">
                  <div class="bar"><span :style="{ width: `${Math.round((g.tokens / groupTotal) * 100)}%` }" /></div>
                  <span class="muted small">{{ tokens(g.input_tokens) }} in · {{ tokens(g.output_tokens) }} out</span>
                </td>
                <td class="num">{{ tokens(g.tokens) }}</td>
                <td class="num">{{ g.turns }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="panel recent">
          <div class="panel-head"><h3>Recent calls</h3><span class="muted small">Last 100</span></div>
          <p v-if="recordsFailed" class="muted">Could not load recent calls.</p>
          <p v-else-if="records.length === 0" class="muted">None.</p>
          <ul v-else class="calls">
            <template v-for="t in turns" :key="t.id">
              <UsageCall v-if="t.rows.length === 1" :record="t.rows[0]!" />
              <li v-else class="turn">
                <button
                  type="button"
                  class="turn-head"
                  :aria-expanded="openTurns.has(t.id)"
                  :aria-label="`${t.lead} and ${t.rows.length - 1} more calls for one response`"
                  @click="toggleTurn(t.id)"
                >
                  <svg class="chevron" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>
                  <span class="turn-main">
                    <span class="call-agent">{{ t.lead }}</span>
                    <span class="chip">{{ t.rows.length }} calls</span>
                    <span class="muted small turn-time">{{ localTime(t.at) }}</span>
                  </span>
                  <strong class="turn-total">{{ tokens(t.total) }}</strong>
                </button>
                <ul v-if="openTurns.has(t.id)" class="turn-calls">
                  <UsageCall v-for="r in t.rows" :key="r.id" :record="r" />
                </ul>
              </li>
            </template>
          </ul>
        </div>


</section>
</template>
<style scoped>
.usage-details { min-width: 0; overflow-wrap: anywhere; }
.usage-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.head {
  align-items: last baseline;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

h3 {
  margin: 0;
  font-size: 1em;
}
h4 {
  margin: 16px 0 8px;
  font-size: 0.85em;
  font-weight: 600;
  color: var(--muted);
}
.ranges {
  align-items: last baseline;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.ranges > .segmented-control {
  flex: 1 1 auto;
}
.ranges > .export {
  flex: 0 0 auto;
}
@media (max-width: 767px) {
  .ranges { width: 100%; flex-wrap: nowrap; }
}
.panel {
  margin-top: 12px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.panel-head {
  align-items: last baseline;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px 12px;
  margin-bottom: 12px;
}
.panel-head .small {
  margin: 0;
}
.activity :deep(.chart button.chip) {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-size: 0.8em;
}
.activity :deep(.chart button.chip:focus-visible) {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.limit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}
.limit-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 12px;
  margin-bottom: 8px;
  font-size: 0.9em;
}
.bar {
  height: 6px;
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
.small {
  margin: 6px 0 0;
  font-size: 0.8em;
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.stat {
  display: flex;
  flex-direction: column;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--code-bg);
}
.stat strong {
  font-size: 1.3em;
  font-variant-numeric: tabular-nums;
}
.stat span {
  font-size: 0.8em;
  color: var(--muted);
}
.insights {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 14px 0 0;
  font-size: 0.8em;
  color: var(--muted);
}
.insight strong {
  font-weight: 600;
  color: var(--text);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9em;
}
th,
td {
  padding: 8px;
  border-top: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}
th {
  padding-top: 0;
  border-top: none;
  font-size: 0.8em;
  font-weight: 500;
  color: var(--muted);
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.share {
  width: 45%;
}
.share .small {
  display: block;
  margin-top: 3px;
}
.calls {
  margin: 0;
  padding: 0;
  list-style: none;
}
/* A response with several calls: one header row, its calls indented under it. */
.turn {
  border-top: 1px solid var(--border);
  font-size: 0.9em;
}
.turn:first-child {
  border-top: none;
}
.turn-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 0;
  border: none;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: var(--text);
  background: transparent;
}
.turn:first-child .turn-head {
  padding-top: 0;
}
.chevron {
  flex: none;
  fill: none;
  stroke: var(--muted);
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform 0.15s ease;
}
.turn-head[aria-expanded='true'] .chevron {
  transform: rotate(90deg);
}
.turn-main {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.turn-main .call-agent {
  font-weight: 500;
}
.turn-time {
  display: block;
  margin: 2px 0 0;
}
.turn-total {
  flex: none;
  font-variant-numeric: tabular-nums;
}
.turn-calls {
  margin: 0 0 6px 20px;
  padding: 0 0 0 12px;
  border-left: 2px solid var(--border);
  list-style: none;
}
.turn-calls :deep(.call:first-child) {
  padding-top: 4px;
}
.chip {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 0.8em;
  color: var(--muted);
  background: var(--code-bg);
}
.muted {
  color: var(--muted);
}
.error {
  color: var(--danger);
}
</style>
