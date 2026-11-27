/** The three allowance actions of the Usage page: their form, its checks, the texts and the request. */
import {
  usageAllowanceClient, type AllowanceResult, type Recipients, type ResetKind, type WindowName,
} from "../api/UsageAllowanceClient";

export type AllowanceAction = "resets" | "clear" | "boost";

export interface AllowanceForm {
  all: boolean;
  ids: number[];
  /** The reset kind, or the windows a reset of usage or a boost covers. */
  windows: ResetKind;
  /** Number fields hold text while empty. */
  count: number | string;
  percent: number | string;
  /** A `datetime-local` value (local time): the expiry of a reset, or the end of a boost. */
  until: string;
}

export interface AllowanceOutcome {
  kind: "ok" | "warning" | "error";
  text: string;
}

export const ACTION_LABELS: Record<AllowanceAction, string> = {
  resets: "Send resets", clear: "Reset usage", boost: "Boost limits",
};
export const KIND_OPTIONS: { value: ResetKind; label: string }[] = [
  { value: "six_hour", label: "6 hours" }, { value: "weekly", label: "Week" }, { value: "both", label: "Both" },
];
export const RESET_TITLES: Record<ResetKind, string> = {
  six_hour: "6-hour reset", weekly: "Weekly reset", both: "6-hour and weekly reset",
};
const WORDS: Record<ResetKind, string> = { six_hour: "6-hour", weekly: "weekly", both: "6-hour and weekly" };
const DONE: Record<AllowanceAction, string> = {
  resets: "Resets sent to", clear: "Usage reset for", boost: "Limits boosted for",
};

export const blankForm = (): AllowanceForm => ({ all: false, ids: [], windows: "six_hour", count: 1, percent: 50, until: "" });

export const windowsLabel = (windows: WindowName[]): string => windows.map((name) => WORDS[name]).join(" and ");

const windowsOf = (kind: ResetKind): WindowName[] => (kind === "both" ? ["six_hour", "weekly"] : [kind]);

const accountsText = (count: number): string => `${count} account${count === 1 ? "" : "s"}`;

function whole(value: number | string, max: number): boolean {
  const n = Number(value);
  return value !== "" && Number.isInteger(n) && n >= 1 && n <= max;
}

/** Why the form cannot be sent yet, or "". */
export function formProblem(action: AllowanceAction, form: AllowanceForm, now = Date.now()): string {
  if (!form.all && !form.ids.length) return "Choose at least one user.";
  if (action === "resets" && !whole(form.count, 20)) return "Send 1 to 20 resets.";
  if (action === "boost" && !whole(form.percent, 1000)) return "Boost by 1 to 1000 percent.";
  if (action === "boost" && !form.until) return "Choose when the boost ends.";
  if (action !== "clear" && form.until && !(new Date(form.until).getTime() > now)) {
    return action === "boost" ? "The end must be in the future." : "The expiry must be in the future.";
  }
  return "";
}

export const needsConfirm = (action: AllowanceAction, form: AllowanceForm): boolean => action === "clear" || form.all;

export function confirmText(action: AllowanceAction, form: AllowanceForm, enabled: number): string {
  const who = form.all ? `all ${enabled} enabled account${enabled === 1 ? "" : "s"}` : accountsText(form.ids.length);
  const words = WORDS[form.windows];
  if (action === "resets") return `Send ${form.count} free ${words} reset${Number(form.count) === 1 ? "" : "s"} to ${who}?`;
  if (action === "clear") return `Reset ${words} usage of ${who}? This cannot be undone.`;
  return `Boost ${words} limits by ${form.percent}% for ${who}?`;
}

export function resultMessage(action: AllowanceAction, { done, failed }: AllowanceResult): AllowanceOutcome {
  const text = `${DONE[action]} ${accountsText(done)}.`;
  if (!failed.length) return { kind: "ok", text };
  return { kind: done ? "warning" : "error", text: `${text} Not done for: ${failed.join(", ")}.` };
}

export function sendAllowance(action: AllowanceAction, form: AllowanceForm): Promise<AllowanceResult> {
  const to: Recipients = form.all ? { all: true } : { account_ids: form.ids };
  const windows = windowsOf(form.windows);
  const until = form.until ? new Date(form.until).toISOString() : "";
  if (action === "clear") return usageAllowanceClient.clear({ ...to, windows });
  if (action === "boost") return usageAllowanceClient.boost({ ...to, windows, percent: Number(form.percent), ends_at: until });
  return usageAllowanceClient.grant({
    ...to, kind: form.windows, count: Number(form.count), ...(until ? { expires_at: until } : {}),
  });
}
