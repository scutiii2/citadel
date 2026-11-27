import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { usageClient } from "../api/UsageClient";
import type { UsageOverview } from "../../../api/contracts/usage";
import { useAuthStore } from "../../../stores/auth";
import { formatUtc } from "../../../utils/time";
import { usagePercent } from "../../../utils/analytics/usageFormat";

/** The account's token limits, free resets and automatic switch, as the header's ring and the Usage page show them;
 * the chat view reads them again when an answer ends. A failed read keeps the old numbers; the Usage page is where
 * errors belong. */
export const useUsageLimitsStore = defineStore("usageLimits", () => {
  const auth = useAuthStore();
  const usage = ref<UsageOverview | null>(null);
  let seq = 0; // the newest read: an older answer is dropped
  let epoch = 0; // the signed-in account

  async function load(): Promise<void> {
    const mine = (seq += 1);
    try {
      const result = await usageClient.mine(1);
      if (mine === seq) usage.value = result;
    } catch {
      // keep what is shown
    }
  }

  /** Sends a change and shows what the server answers with. A refusal is thrown to the caller. */
  async function change(request: () => Promise<UsageOverview>): Promise<void> {
    const mine = epoch;
    const result = await request();
    if (mine !== epoch) return;
    seq += 1; // a read still on its way may hold the numbers from before the change
    usage.value = result;
  }

  const spend = (id: string) => change(() => usageClient.spendReset(id));
  const setAutoUse = (enabled: boolean) => change(() => usageClient.setAutoReset(enabled));

  // Another account must never see these, nor a late answer for the one before.
  watch(() => auth.account?.id, () => {
    seq += 1;
    epoch += 1;
    usage.value = null;
  }, { flush: "sync" });

  /** Only the windows that have a limit. */
  const windows = computed(() => {
    const u = usage.value;
    if (!u) return [];
    return [
      { key: "6 h", title: "Last 6 hours", window: u.six_hour },
      { key: "Week", title: "Last 7 days", window: u.weekly },
    ]
      .filter((entry) => entry.window.limit > 0)
      .map((entry) => ({ ...entry, percent: usagePercent(entry.window) }));
  });

  return { usage, windows, load, spend, setAutoUse };
});

export type LimitWindow = ReturnType<typeof useUsageLimitsStore>["windows"][number];

/** When the oldest tokens drop out of a window, or "" with nothing used. */
export function resetText({ window }: LimitWindow): string {
  return window.reset_at && window.used ? `Oldest tokens stop counting at ${formatUtc(window.reset_at)}.` : "";
}
