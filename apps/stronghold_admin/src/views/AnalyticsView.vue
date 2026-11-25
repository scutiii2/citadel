<script setup lang="ts">
import { PageLayout } from "@citadel/ui";
import { computed, onMounted, ref, watch } from "vue";
import { logsClient, type AnalyticsRange, type AnalyticsReport, type LogActor, type LogKind } from "../api/LogsClient";
import { AdminSearch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import ActivityChart from "../components/analytics/ActivityChart.vue";
import BarList from "../components/analytics/BarList.vue";
import HourHeatmap from "../components/analytics/HourHeatmap.vue";
import KindStatTile from "../components/analytics/KindStatTile.vue";
import TrafficPanel from "../components/analytics/TrafficPanel.vue";
import "@citadel/ui/infoPage.css";
import "@citadel/ui/admin.css";
import LogEntries from "../components/LogEntries.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import { LOG_PERMISSIONS } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { errorMessage } from "../utils/errors";
import { KIND_COLORS, KIND_LABELS, RANGE_OPTIONS, accountLabel } from "../utils/logAnalytics";

/** Analytics page (was Logs): charts over the log entries (Overview), network
 * traffic (Traffic) and the entries themselves (Entries). Any `logs.*` permission
 * opens Overview and Entries and `traffic.view` opens Traffic; portcullis only
 * counts the kinds the account may read, so the page just draws what it gets. */

type Tab = "overview" | "traffic" | "entries";

// Rows per kind in the ranking cards; portcullis sends up to ten.
const TOP_SHOWN = 5;

const auth = useAuthStore();
const canLogs = computed(() => LOG_PERMISSIONS.some((permission) => auth.hasPermission(permission)));
const canTraffic = computed(() => auth.hasPermission("traffic.view"));
const TAB_OPTIONS = computed<{ value: Tab; label: string }[]>(() => [
  ...(canLogs.value ? [{ value: "overview" as const, label: "Overview" }] : []),
  ...(canTraffic.value ? [{ value: "traffic" as const, label: "Traffic" }] : []),
  ...(canLogs.value ? [{ value: "entries" as const, label: "Entries" }] : []),
]);

const search = ref("");
const tab = ref<Tab>(canLogs.value ? "overview" : "traffic");
const range = ref<AnalyticsRange>("7d");
const report = ref<AnalyticsReport | null>(null);
const loading = ref(false);
const error = ref("");
// Set when an account's row was clicked: the Entries tab opens on its list.
const jump = ref<{ kind: LogKind; actor: LogActor } | null>(null);
// The Traffic tab fetches its own report; this asks it to fetch again.
const trafficRefresh = ref(0);
const trafficLoading = ref(false);
const busy = computed(() => (tab.value === "traffic" ? trafficLoading.value : loading.value));

const kindParts = computed(() =>
  (report.value?.kinds ?? []).map((kind) => ({ id: kind, label: KIND_LABELS[kind], color: KIND_COLORS[kind] })),
);
const trend = (kind: LogKind): number[] => report.value?.series.map((p) => p.counts[kind] ?? 0) ?? [];
const sources = computed(() =>
  (report.value?.kinds ?? []).map((kind) => ({
    kind,
    items: (report.value?.top_sources[kind] ?? []).slice(0, TOP_SHOWN).map((s) => ({ key: s.source, label: s.source, count: s.count })),
  })),
);
const accounts = computed(() =>
  (report.value?.kinds ?? []).map((kind) => ({
    kind,
    items: (report.value?.accounts[kind] ?? []).slice(0, TOP_SHOWN).map((a) => ({
      key: (a.account_id ?? "server") as LogActor,
      label: accountLabel(a),
      count: a.count,
    })),
  })),
);

async function load(): Promise<void> {
  if (!canLogs.value) return;
  const asked = range.value;
  loading.value = true;
  error.value = "";
  try {
    const result = await logsClient.analytics(asked);
    if (range.value === asked) report.value = result;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    if (range.value === asked) loading.value = false;
  }
}

function showTab(next: Tab): void {
  jump.value = null;
  tab.value = next;
}

function refresh(): void {
  if (tab.value === "traffic") trafficRefresh.value += 1;
  else void load();
}

function openEntries(kind: LogKind, actor: LogActor): void {
  jump.value = { kind, actor };
  tab.value = "entries";
}

onMounted(load);
watch(range, load);
</script>

<template>
  <PageLayout class="admin-panel" title="Analytics" wide>
    <section class="admin-panel-card" aria-labelledby="analytics-title">
      <header class="admin-panel-head">
        <h2 id="analytics-title">Analytics</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Analytics">
            <p>Review workspace activity, errors, and network traffic. Times are in UTC.</p>
            <p>Overview and Entries need a log permission; Traffic needs traffic.view. Open a ranked account to see its entries.</p>
          </PanelHelp>
          <div class="toolbar">
            <SegmentedControl :model-value="tab" :options="TAB_OPTIONS" label="View" aria-label="View" @update:model-value="showTab" />
            <SegmentedControl v-if="tab !== 'entries'" v-model="range" :options="RANGE_OPTIONS" label="Period" aria-label="Range" />
          </div>
          <button v-if="tab !== 'entries'" type="button" class="admin-icon" title="Refresh" aria-label="Refresh" :disabled="busy" :aria-busy="busy" @click="refresh">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" /></svg>
          </button>
          <AdminSearch v-else v-model="search" label="Search entries" />
        </div>
      </header>
      <div class="analytics-body">
      <template v-if="tab === 'overview'">
        <p v-if="error" class="error">{{ error }}</p>
        <p v-else-if="!report" class="muted" role="status">Loading analytics…</p>
        <div v-if="report" :class="['overview', { dim: loading }]">
          <div class="tiles">
            <KindStatTile
              v-for="kind in report.kinds"
              :key="kind"
              :kind="kind"
              :total="report.totals[kind]!"
              :trend="trend(kind)"
              :range="report.period"
            />
          </div>

          <div class="card">
            <h3>Over time</h3>
            <ActivityChart :series="report.series" :parts="kindParts" :bucket="report.bucket" noun="entries" />
          </div>

          <div class="pair">
            <div class="card">
              <h3>Top sources</h3>
              <div v-for="group in sources" :key="group.kind" class="group">
                <h4><span class="key" :style="{ background: KIND_COLORS[group.kind] }" />{{ KIND_LABELS[group.kind] }}</h4>
                <BarList :items="group.items" :color="KIND_COLORS[group.kind]" />
              </div>
            </div>
            <div class="card">
              <h3>Busiest accounts</h3>
              <div v-for="group in accounts" :key="group.kind" class="group">
                <h4><span class="key" :style="{ background: KIND_COLORS[group.kind] }" />{{ KIND_LABELS[group.kind] }}</h4>
                <BarList
                  :items="group.items"
                  :color="KIND_COLORS[group.kind]"
                  selectable
                  @select="(actor) => openEntries(group.kind, actor)"
                />
              </div>
            </div>
          </div>

          <div class="card">
            <h3>When it happens</h3>
            <HourHeatmap :cells="report.heatmap" />
          </div>
        </div>
      </template>

      <TrafficPanel v-else-if="tab === 'traffic'" v-model:loading="trafficLoading" :range="range" :refresh="trafficRefresh" />

      <LogEntries v-else :kind="jump?.kind" :actor="jump?.actor" :search="search" />


      </div>
    </section>
  </PageLayout>
</template>

<style scoped src="../components/analytics/overview.css"></style>
<style scoped>
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.analytics-body { padding: 14px 16px; }
</style>
