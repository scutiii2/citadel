import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import { usageClient, type MyUsage } from "../api/UsageClient";
import { useAuthStore } from "../../../stores/auth";
import { formatUtc } from "../../../utils/time";
import { usagePercent } from "../../../utils/analytics/usageFormat";

/** The account's 6-hour and weekly token limits, read once for everything that shows them (the header's ring and
 * the chat list's gauges). A failed read keeps the old numbers; the Usage page is where errors belong. */
export const useUsageLimitsStore = defineStore("usageLimits", () => {
  const auth = useAuthStore();
  const usage = ref<MyUsage | null>(null);
  let seq = 0;

  async function load(): Promise<void> {
    const mine = (seq += 1);
    try {
      const result = await usageClient.mine(1);
      if (mine === seq) usage.value = result;
    } catch {
      // keep what is shown
    }
  }

  // Another account must never see these, nor a late answer for the one before.
  watch(() => auth.account?.id, () => {
    seq += 1;
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

  return { windows, load };
});

export type LimitWindow = ReturnType<typeof useUsageLimitsStore>["windows"][number];

/** When the oldest tokens drop out of a window, or "" with nothing used. */
export function resetText({ window }: LimitWindow): string {
  return window.reset_at && window.used ? `Oldest tokens stop counting at ${formatUtc(window.reset_at)}.` : "";
}
