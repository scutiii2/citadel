<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { tuningClient, type InsightsView } from "../api/TuningClient";
import ActionMessage from "../components/admin/ActionMessage.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import StatTile from "../components/admin/StatTile.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** What Legion's routing, confidentiality check and tool batching did over the last days, from the daily counters. */
const days = ref(7);
const data = ref<InsightsView | null>(null);
const error = ref("");
const loading = ref(false);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    data.value = await tuningClient.insights(days.value);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

/** Each counter summed over the shown days. */
const total = computed(() => {
  const sums: Record<string, number> = {};
  for (const day of Object.values(data.value?.history ?? {})) for (const [name, value] of Object.entries(day)) sums[name] = (sums[name] ?? 0) + value;
  return sums;
});
const n = (name: string) => total.value[name] ?? 0;
const sumOf = (prefix: string) => Object.entries(total.value).filter(([name]) => name.startsWith(prefix)).reduce((all, [, value]) => all + value, 0);
const percent = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : "–");

/** Tokens used today per user and per agent, biggest first. */
const today = computed(() => {
  const dates = Object.keys(data.value?.history ?? {}).sort();
  const latest = data.value?.history[dates[dates.length - 1] ?? ""] ?? {};
  const rows = (prefix: string) => Object.entries(latest).filter(([name]) => name.startsWith(prefix))
    .map(([name, value]) => ({ name: name.slice(prefix.length), value })).sort((a, b) => b.value - a.value).slice(0, 10);
  return { users: rows("tokens.user."), agents: rows("tokens.agent.") };
});
const tiers = ["light", "standard", "heavy", "none"];
const reasons: [string, string][] = [["check", "Found by the check"], ["tool_result", "Found in tool results"], ["recall", "Recalled notes or skills"], ["private", "Private extensions"]];
</script>

<template>
  <PageLayout class="admin-panel" title="Insights" wide>
    <section class="admin-panel-card" aria-labelledby="insights-title">
      <header class="admin-panel-head">
        <h2 id="insights-title">Last {{ days }} days</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Insights">Counts of what Legion did, per UTC day, kept for 35 days. Use them to tune the Router's confidence, the confidentiality check and the tool-call limits on the Tuning page.</PanelHelp>
          <label class="range">
            <span class="sr-only">Days shown</span>
            <select v-model.number="days" data-test="days" @change="load">
              <option :value="7">7 days</option>
              <option :value="14">14 days</option>
              <option :value="30">30 days</option>
            </select>
          </label>
        </div>
      </header>
      <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text"><button type="button" class="small" @click="load">Retry</button></ActionMessage>
      <p v-else-if="!data" class="admin-panel-text muted" role="status">Loading insights…</p>
      <template v-else>
        <section class="group" aria-labelledby="routing-title">
          <h3 id="routing-title">Routing <PanelHelp title="Routing">The Router picks a specialist and a model tier before Ember plans. An unsure pick leaves the turn with Ember. Unavailable means the Router was off or failed, so Ember used the default model.</PanelHelp></h3>
          <div class="tiles">
            <StatTile label="Turns routed" :value="n('router.turns')" />
            <StatTile label="Agent picked" :value="n('router.agent_picked')" />
            <StatTile label="Left to Ember" :value="n('router.agent_uncertain')" />
            <StatTile label="Sent straight to a specialist" :value="n('router.dispatched')" />
            <StatTile label="Router unavailable" :value="n('router.unavailable')" warn />
          </div>
          <p class="note">Picked share: {{ percent(n("router.agent_picked"), n("router.turns")) }}. Tier chosen:
            <span v-for="tier in tiers" :key="tier" class="chip-text">{{ tier === "none" ? "default" : tier }} {{ n("router.tier." + tier) }}</span></p>
        </section>
        <section class="group" aria-labelledby="conf-title">
          <h3 id="conf-title">Confidential data <PanelHelp title="Confidential data">A confidential turn uses only trusted gateways. Refused means no trusted gateway could take it, so nothing was sent. Failed closed means the check could not answer (Jev down or slow) and the turn was treated as confidential.</PanelHelp></h3>
          <div class="tiles">
            <StatTile label="Checks run" :value="n('confidential.checks')" />
            <StatTile label="Turns marked confidential" :value="sumOf('confidential.marked.')" />
            <StatTile label="Moved to a trusted gateway" :value="n('confidential.switches')" />
            <StatTile label="Checker unsure" :value="n('confidential.unsure')" />
            <StatTile label="Failed closed" :value="n('confidential.failed_closed')" warn />
            <StatTile label="Refused" :value="n('confidential.refused')" warn />
          </div>
          <p class="note">Marked by reason:
            <span v-for="[key, label] in reasons" :key="key" class="chip-text">{{ label }} {{ n("confidential.marked." + key) }}</span></p>
        </section>
        <section class="group" aria-labelledby="batch-title">
          <h3 id="batch-title">Tool calls <PanelHelp title="Tool calls">Calls from one model round that only read run at the same time. The batch tool lets a specialist send several calls, with dependencies, in one step. Failed steps include steps skipped because one they needed failed.</PanelHelp></h3>
          <div class="tiles">
            <StatTile label="Rounds with parallel calls" :value="n('batch.parallel_groups')" />
            <StatTile label="Calls run together" :value="n('batch.parallel_calls')" />
            <StatTile label="Batches submitted" :value="n('batch.run_tools')" />
            <StatTile label="Batch steps" :value="n('batch.run_tools_steps')" />
            <StatTile label="Batch steps failed" :value="n('batch.run_tools_failed_steps')" warn />
          </div>
        </section>
        <section class="group" aria-labelledby="tokens-title">
          <h3 id="tokens-title">Tokens today <PanelHelp title="Tokens today">What each user and agent used since midnight UTC, counted when a turn ends. Daily budgets on the Tuning page stop new turns when a total reaches its limit.</PanelHelp></h3>
          <p class="note">Daily budget per user: {{ data.budgets.daily_tokens_per_user ? data.budgets.daily_tokens_per_user.toLocaleString() : "no limit" }}. Per agent: {{ data.budgets.daily_tokens_per_agent ? data.budgets.daily_tokens_per_agent.toLocaleString() : "no limit" }}.</p>
          <div class="pair">
            <table class="admin-records" data-test="users">
              <caption class="sr-only">Tokens used today per user</caption>
              <thead><tr><th scope="col">User</th><th scope="col" class="num">Tokens</th></tr></thead>
              <tbody>
                <tr v-for="row in today.users" :key="row.name"><th scope="row">{{ row.name }}</th><td class="num">{{ row.value.toLocaleString() }}</td></tr>
                <tr v-if="!today.users.length"><td colspan="2" class="muted">No usage counted today.</td></tr>
              </tbody>
            </table>
            <table class="admin-records" data-test="agents">
              <caption class="sr-only">Tokens used today per agent</caption>
              <thead><tr><th scope="col">Agent</th><th scope="col" class="num">Tokens</th></tr></thead>
              <tbody>
                <tr v-for="row in today.agents" :key="row.name"><th scope="row">{{ row.name }}</th><td class="num">{{ row.value.toLocaleString() }}</td></tr>
                <tr v-if="!today.agents.length"><td colspan="2" class="muted">No usage counted today.</td></tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </section>
  </PageLayout>
</template>

<style scoped>
.group { padding: 14px 16px; }
.group + .group { border-top: 1px solid var(--border); }
.group h3 { display: flex; align-items: center; gap: 4px; margin: 0 0 10px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }
.note { margin: 10px 0 0; color: var(--muted); font-size: 0.9rem; }
.chip-text { margin-left: 10px; white-space: nowrap; }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
select { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
