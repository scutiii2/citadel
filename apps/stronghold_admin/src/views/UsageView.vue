<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usageClient, type AccountUsage, type MyUsage, type UsageGroupBy, type UsageRecordRow } from "../api/UsageClient";
import { ApiError } from "../api/http";
import { AdminSearch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { StatTile } from "@citadel/ui";
import { RecordDrawer } from "@citadel/ui";
import SegmentedControl from "../components/SegmentedControl.vue";
import UsageDetails from "../components/usage/UsageDetails.vue";
import AccountAllowances from "../components/usage/AccountAllowances.vue";
import AllowanceDrawer from "../components/usage/AllowanceDrawer.vue";
import { ACTION_LABELS, type AllowanceAction, type AllowanceOutcome } from "../utils/allowance";
import { useAuthStore } from "../stores/auth";
import { downloadText, exportFileName } from "../utils/downloadText";
import { errorMessage, formatUtc } from "../utils/errors";
import { usageToMarkdown } from "../utils/usageExport";
import { monthStart, utcDay } from "../utils/usageStats";
import "@citadel/ui/admin.css";

const auth = useAuthStore();
const canManage = computed(() => auth.hasPermission("settings.manage"));
const ALLOWANCE_ACTIONS: { id: AllowanceAction; icon: string }[] = [
  { id: "resets", icon: "M20 12v9H4v-9M2 7h20v5H2zM12 21V7M12 7H7.5a2.5 2.5 0 1 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 1 0 0-5C13 2 12 7 12 7z" },
  { id: "clear", icon: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" },
  { id: "boost", icon: "M13 2 3 14h9l-1 8 10-12h-9z" },
];
const action = ref<AllowanceAction | null>(null);
const outcome = ref<AllowanceOutcome | null>(null);

function openAction(next: AllowanceAction) {
  outcome.value = null;
  action.value = next;
}

function actionDone(result: AllowanceOutcome) {
  action.value = null;
  outcome.value = result;
}
const RANGES = [
  { value: "month", label: "This month", days: 30 },
  { value: "7d", label: "7 days", days: 7 },
  { value: "30d", label: "30 days", days: 30 },
  { value: "90d", label: "90 days", days: 90 },
  { value: "12m", label: "12 months", days: 365 },
] as const;
type RangeKey = (typeof RANGES)[number]["value"];
const range = ref<RangeKey>("30d");
const groupBy = ref<UsageGroupBy>("agent");
const currentRange = computed(() => RANGES.find(r => r.value === range.value)!);
function period() { return { days: currentRange.value.days, since: range.value === "month" ? monthStart(new Date()) : undefined }; }
const accounts = ref<AccountUsage[]>([]);
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return accounts.value.filter((user) => user.username.toLowerCase().includes(query));
});
const totals = computed(() => ({
  tokens: accounts.value.reduce((sum, user) => sum + user.tokens, 0),
  turns: accounts.value.reduce((sum, user) => sum + user.turns, 0),
  active: accounts.value.filter((user) => user.tokens > 0).length,
  top: Math.max(1, ...accounts.value.map((user) => user.tokens)),
}));
const selected = ref<AccountUsage | null>(null);
const summaryLoading = ref(false);
const summaryError = ref("");
const detailLoading = ref(false);
const detailError = ref("");
const loaded = ref<{ usage: MyUsage; username: string; rangeLabel: string; rangeKey: RangeKey } | null>(null);
const records = ref<UsageRecordRow[]>([]);
const recordsFailed = ref(false);
const year = ref<MyUsage | null>(null);
const yearFailed = ref(false);
let summaryRequest = 0;
let detailRequest = 0;
let yearRequest = 0;

function clearDetail() {
  ++detailRequest;
  ++yearRequest;
  loaded.value = null;
  records.value = [];
  recordsFailed.value = false;
  year.value = null;
  yearFailed.value = false;
  detailError.value = "";
  detailLoading.value = false;
}

async function loadSummary() {
  const request = ++summaryRequest;
  summaryLoading.value = true;
  summaryError.value = "";
  accounts.value = [];
  const { days, since } = period();
  try {
    const rows = await usageClient.allAccounts(days, since);
    if (request !== summaryRequest) return;
    accounts.value = rows;
    if (selected.value && !rows.some(row => row.account_id === selected.value!.account_id)) selected.value = null;
  } catch (err) {
    if (request === summaryRequest) summaryError.value = errorMessage(err);
  } finally {
    if (request === summaryRequest) summaryLoading.value = false;
  }
}

function deletedTarget() {
  selected.value = null;
  void loadSummary();
}

async function loadDetails() {
  const user = selected.value;
  if (!user) return;
  const request = ++detailRequest;
  loaded.value = null;
  records.value = [];
  recordsFailed.value = false;
  detailError.value = "";
  detailLoading.value = true;
  const { days, since } = period();
  const rangeLabel = currentRange.value.label;
  const rangeKey = range.value;
  try {
    let failed = false;
    const [report, rows] = await Promise.all([
      usageClient.account(user.account_id, days, since, { groupBy: groupBy.value }),
      usageClient.records(user.account_id, days, since, { limit: 100 }).catch(err => {
        if (err instanceof ApiError && err.status === 404) throw err;
        failed = true;
        return [];
      }),
    ]);
    if (request !== detailRequest) return;
    loaded.value = { usage: report, username: user.username, rangeLabel, rangeKey };
    records.value = rows;
    recordsFailed.value = failed;
  } catch (err) {
    if (request !== detailRequest) return;
    if (err instanceof ApiError && err.status === 404) deletedTarget();
    else detailError.value = errorMessage(err);
  } finally {
    if (request === detailRequest) detailLoading.value = false;
  }
}

async function loadYear() {
  const user = selected.value;
  if (!user) return;
  const request = ++yearRequest;
  year.value = null;
  yearFailed.value = false;
  try {
    const report = await usageClient.account(user.account_id, 366);
    if (request === yearRequest) year.value = report;
  } catch (err) {
    if (request !== yearRequest) return;
    if (err instanceof ApiError && err.status === 404) deletedTarget();
    else yearFailed.value = true;
  }
}

function exportReport() {
  const snapshot = loaded.value;
  if (!snapshot) return;
  const now = new Date();
  downloadText(exportFileName(`usage-${snapshot.username}-${snapshot.rangeKey}-${utcDay(now)}`, "md"),
    usageToMarkdown(snapshot.usage.report, { username: snapshot.username, rangeLabel: snapshot.rangeLabel, generatedAt: now }), "text/markdown");
}

watch(() => selected.value?.account_id, () => {
  clearDetail();
  if (selected.value) { void loadDetails(); void loadYear(); }
}, { flush: "sync" });
watch(range, () => { void loadSummary(); void loadDetails(); }, { flush: "sync" });
watch(groupBy, () => { void loadDetails(); }, { flush: "sync" });
watch(() => auth.account?.id, () => {
  ++summaryRequest;
  accounts.value = [];
  selected.value = null;
  action.value = null;
  outcome.value = null;
  clearDetail();
  summaryLoading.value = false;
  summaryError.value = "";
  if (auth.hasPermission("usage.all.view")) void loadSummary();
}, { flush: "sync" });
onBeforeUnmount(() => { ++summaryRequest; clearDetail(); });
onMounted(() => { if (auth.hasPermission("usage.all.view")) void loadSummary(); });
</script>

<template>
  <PageLayout class="usage-view admin-panel" title="Usage" wide>
    <div v-if="accounts.length && !summaryError" class="stats" aria-label="Totals for the period">
      <StatTile label="Accounts" :value="accounts.length" />
      <StatTile label="Accounts with usage" :value="totals.active" />
      <StatTile label="Tokens" :value="totals.tokens" />
      <StatTile label="Answers" :value="totals.turns" />
    </div>
    <section class="admin-panel-card" aria-labelledby="usage-title" :aria-busy="summaryLoading">
      <header class="admin-panel-head">
        <h2 id="usage-title">All users</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Usage">
            <p>Review each user's token usage and account limits for the chosen period.</p>
            <p>Open a user to see their usage by agent, provider, gateway or model, and to export it as Markdown.</p>
            <p v-if="canManage">Send free resets, reset usage or boost limits with the buttons here; open a user to remove their resets and boosts.</p>
          </PanelHelp>
          <template v-if="canManage">
            <button v-for="item in ALLOWANCE_ACTIONS" :key="item.id" type="button" class="admin-icon" :aria-label="ACTION_LABELS[item.id]" :title="ACTION_LABELS[item.id]" aria-haspopup="dialog" :disabled="!accounts.length" @click="openAction(item.id)">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" /></svg>
            </button>
          </template>
          <div class="ranges"><SegmentedControl v-model="range" :options="RANGES" label="Period" aria-label="Period" /></div>
          <AdminSearch ref="searchField" v-model="search" label="Search users" />
        </div>
      </header>
      <ActionMessage v-if="outcome" :kind="outcome.kind" :text="outcome.text" class="admin-panel-text" />
      <ActionMessage v-if="summaryError" kind="error" :text="`Could not load user usage: ${summaryError}`" class="admin-panel-text"><button type="button" class="chip summary-retry" @click="loadSummary">Retry</button></ActionMessage>
      <p v-else-if="summaryLoading" class="admin-panel-text muted" role="status">Loading user usage…</p>
      <p v-else-if="accounts.length === 0" class="admin-panel-text muted">No accounts.</p>
      <p v-else-if="visible.length === 0" class="admin-panel-text muted">No users match. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <div v-else class="admin-table-scroll" role="region" aria-labelledby="usage-title" tabindex="0">
        <table class="admin-records">
          <thead><tr><th scope="col">User</th><th scope="col" class="num">Tokens</th><th scope="col" class="num">Answers</th><th scope="col">Last used in period</th></tr></thead>
          <tbody>
            <tr v-for="user in visible" :key="user.account_id">
              <th scope="row">
                <div class="admin-record-name">
                  <span class="admin-record-badge" aria-hidden="true">{{ user.username.slice(0, 2).toUpperCase() }}</span>
                  <button type="button" class="admin-row-button" aria-haspopup="dialog" :aria-label="`View usage for ${user.username}`" @click="selected = user">{{ user.username }}</button>
                </div>
              </th>
              <td class="num"><span class="tokens">{{ user.tokens.toLocaleString() }}</span><span class="share" aria-hidden="true"><span :style="{ width: `${Math.round((user.tokens / totals.top) * 100)}%` }"></span></span></td>
              <td class="num">{{ user.turns.toLocaleString() }}</td>
              <td>{{ user.last_used_at ? formatUtc(user.last_used_at) : "No usage" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <RecordDrawer :open="selected !== null" :title="selected ? `Usage for ${selected.username}` : 'Usage'" :fallback-focus="() => searchField?.focus()" @close="selected = null">
      <div class="drawer-actions">
        <button type="button" class="admin-icon export" aria-label="Export .md" title="Download the selected user's usage as Markdown" :disabled="!loaded" @click="exportReport">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0-4-4m4 4 4-4M4 19h16" /></svg>
        </button>
      </div>
      <AccountAllowances v-if="canManage && selected" :key="selected.account_id" :account-id="selected.account_id" :username="selected.username" @changed="loadDetails" />
      <p v-if="detailLoading" class="muted" role="status">Loading usage for {{ selected?.username }}…</p>
      <ActionMessage v-else-if="detailError" kind="error" :text="`Could not load usage for ${selected?.username}: ${detailError}`"><button type="button" class="chip detail-retry" @click="loadDetails">Retry</button></ActionMessage>
      <UsageDetails v-if="loaded" :username="loaded.username" :usage="loaded.usage" :year="year" :records="records" :records-failed="recordsFailed" :year-failed="yearFailed" :loading="detailLoading" :group-by="groupBy" @group="groupBy = $event" />
    </RecordDrawer>
    <AllowanceDrawer v-if="canManage" :action="action" :accounts="accounts" :fallback-focus="() => searchField?.focus()" @close="action = null" @done="actionDone" />
  </PageLayout>
</template>

<style scoped>
.ranges { min-width: 0; max-width: 100%; }
.ranges > .segmented-control { flex: 1 1 auto; }
.num { text-align: right; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 14px; }
.tokens { display: block; font-variant-numeric: tabular-nums; }
.share { display: block; height: 4px; margin: 4px 0 0 auto; width: 100%; max-width: 140px; border-radius: var(--radius-full); background: var(--code-bg); overflow: hidden; }
.share > span { display: block; height: 100%; background: var(--accent); }
.drawer-actions { display: flex; justify-content: flex-end; padding-top: 8px; }
.muted { color: var(--muted); }
.error { color: var(--danger); }
</style>
