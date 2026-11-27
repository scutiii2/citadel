<script setup lang="ts">
import { ActionMessage, ConfirmModal } from "@citadel/ui";
import { onBeforeUnmount, onMounted, ref } from "vue";
import { usageAllowanceClient, type AccountAllowance, type FreeReset, type LimitBoost } from "../../api/UsageAllowanceClient";
import { RESET_TITLES, windowsLabel } from "../../utils/allowance";
import { errorMessage, formatUtc } from "../../utils/errors";

/** One account's unused resets and active boosts, each removable after a question. */
const props = defineProps<{ accountId: number; username: string }>();
const emit = defineEmits<{ changed: [] }>();

interface Removal { title: string; message: string; label: string; run: () => Promise<void> }

const allowance = ref<AccountAllowance | null>(null);
const loaded = ref(false);
const loadError = ref("");
const actionError = ref("");
const removal = ref<Removal | null>(null);
const busy = ref(false);
let seq = 0;

async function load(): Promise<void> {
  const mine = (seq += 1);
  loadError.value = "";
  try {
    const all = await usageAllowanceClient.list();
    if (mine !== seq) return;
    allowance.value = all.find((entry) => entry.account_id === props.accountId) ?? null;
    loaded.value = true;
  } catch (err) {
    if (mine === seq) loadError.value = errorMessage(err);
  }
}

function askReset(reset: FreeReset): void {
  removal.value = {
    title: "Remove reset?",
    message: `Remove the unused ${RESET_TITLES[reset.kind].toLowerCase()} of ${props.username}? This cannot be undone.`,
    label: "Remove",
    run: () => usageAllowanceClient.removeReset(props.accountId, reset.id),
  };
}

function askBoost(boost: LimitBoost): void {
  removal.value = {
    title: "End boost?",
    message: `End the +${boost.percent}% ${windowsLabel(boost.windows)} boost of ${props.username} now?`,
    label: "End boost",
    run: () => usageAllowanceClient.removeBoost(props.accountId, boost.id),
  };
}

async function remove(): Promise<void> {
  const chosen = removal.value;
  if (!chosen || busy.value) return;
  busy.value = true;
  actionError.value = "";
  try {
    await chosen.run();
    emit("changed");
  } catch (err) {
    actionError.value = errorMessage(err);
  }
  removal.value = null;
  busy.value = false;
  await load();
}

function dismiss(): void {
  if (!busy.value) removal.value = null;
}

onMounted(load);
onBeforeUnmount(() => { seq += 1; });
</script>

<template>
  <section class="allowances" aria-labelledby="allowances-title">
    <h3 id="allowances-title">Resets and boosts</h3>
    <ActionMessage v-if="actionError" kind="error" :text="actionError" />
    <ActionMessage v-if="loadError" kind="error" :text="`Could not load resets and boosts: ${loadError}`"><button type="button" class="chip" data-test="allowance-retry" @click="load">Retry</button></ActionMessage>
    <p v-else-if="!loaded" class="muted" role="status">Loading resets and boosts…</p>
    <template v-else>
      <h4>Unused resets</h4>
      <p v-if="!allowance?.resets.length" class="muted">No unused resets.</p>
      <ul v-else>
        <li v-for="(reset, index) in allowance.resets" :key="reset.id">
          <span><strong>{{ RESET_TITLES[reset.kind] }}</strong>, {{ reset.expires_at ? `expires ${formatUtc(reset.expires_at)}` : "no expiry" }}</span>
          <button type="button" class="chip danger" data-test="remove-reset" :disabled="busy" :aria-label="`Remove ${RESET_TITLES[reset.kind].toLowerCase()} ${index + 1}`" @click="askReset(reset)">Remove</button>
        </li>
      </ul>
      <h4>Active boosts</h4>
      <p v-if="!allowance?.boosts.length" class="muted">No active boosts.</p>
      <ul v-else>
        <li v-for="(boost, index) in allowance.boosts" :key="boost.id">
          <span><strong>+{{ boost.percent }}% {{ windowsLabel(boost.windows) }}</strong>, until {{ formatUtc(boost.ends_at) }}</span>
          <button type="button" class="chip danger" data-test="end-boost" :disabled="busy" :aria-label="`End boost ${index + 1}`" @click="askBoost(boost)">End</button>
        </li>
      </ul>
    </template>
    <ConfirmModal :open="removal !== null" :title="removal?.title ?? ''" :message="removal?.message ?? ''" :confirm-label="removal?.label" danger :busy="busy" @confirm="remove" @close="dismiss" />
  </section>
</template>

<style scoped>
.allowances { display: grid; gap: 8px; padding-block: 8px 16px; border-bottom: 1px solid var(--border); }
h3, h4 { margin: 0; }
h3 { font-size: 1em; }
h4 { font-size: 0.85em; color: var(--muted); }
ul { display: grid; gap: 6px; max-height: 220px; margin: 0; padding: 0; overflow: auto; scrollbar-gutter: stable; list-style: none; }
li { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; font-size: 0.9em; }
li > span { min-width: 0; overflow-wrap: anywhere; }
li > button { flex: none; }
.muted { margin: 0; color: var(--muted); font-size: 0.85em; }
@media (max-width: 767px) { li > button { min-height: 44px; } }
</style>
