/** How free resets and boosts are grouped and worded. */
import type { FreeReset, ResetKind, UsageOverview, WindowName } from "../../../api/contracts/usage";
import { formatUtc } from "../../../utils/time";

const KINDS: ResetKind[] = ["six_hour", "weekly", "both"];
const TITLES: Record<ResetKind, string> = {
  six_hour: "6-hour reset", weekly: "Weekly reset", both: "6-hour and weekly reset",
};
const COVERS: Record<ResetKind, WindowName[]> = { six_hour: ["six_hour"], weekly: ["weekly"], both: ["six_hour", "weekly"] };
const EFFECT: Record<ResetKind, string> = {
  six_hour: "6-hour usage goes", weekly: "weekly usage goes", both: "6-hour and weekly usage go",
};
const LIMITS: Record<WindowName, string> = { six_hour: "6-hour limit", weekly: "Weekly limit" };

export interface ResetGroup {
  kind: ResetKind;
  title: string;
  count: number;
  /** The one to spend. */
  next: FreeReset;
  /** Whether any window it covers has tokens to clear. */
  clears: boolean;
}

/** One entry per kind the account holds. `resets` come soonest expiry first, so each group's first is the one to spend. */
export function resetGroups(resets: FreeReset[], usage: UsageOverview): ResetGroup[] {
  return KINDS.flatMap((kind) => {
    const own = resets.filter((reset) => reset.kind === kind);
    const next = own[0];
    if (!next) return [];
    return [{ kind, title: TITLES[kind], count: own.length, next, clears: COVERS[kind].some((name) => usage[name].used > 0) }];
  });
}

export const confirmText = (kind: ResetKind): string => `Your ${EFFECT[kind]} back to zero. The reset is used up.`;

export function boostLines(usage: UsageOverview): string[] {
  return (["six_hour", "weekly"] as const).flatMap((name) => {
    const boost = usage[name].boost;
    return boost ? [`${LIMITS[name]}: +${boost.percent}% until ${formatUtc(boost.ends_at)}`] : [];
  });
}

/** "" when cached input counts in full, or the server says nothing about it. */
export function cachedText(weight: number | undefined): string {
  return weight === undefined || weight >= 1 ? "" : `Cached input counts at ${Math.round(weight * 100)}%.`;
}
