/** How the agent asks before it runs a tool. The picker in the chat bar and the Settings page share these. */

export type ApprovalMode = "ask" | "auto" | "allow_all";

export interface ApprovalModeInfo {
  id: ApprovalMode;
  label: string;
  description: string;
}

export const APPROVAL_MODES: readonly ApprovalModeInfo[] = [
  { id: "ask", label: "Ask every time", description: "Every tool waits for your answer." },
  {
    id: "auto",
    label: "Auto",
    description: "Tools that only read run on their own. Anything that changes something still asks.",
  },
  { id: "allow_all", label: "Allow all", description: "No tool asks first." },
];

/** What a new account (or one that never chose) gets: nothing asks, as before the picker existed. */
export const DEFAULT_APPROVAL_MODE: ApprovalMode = "allow_all";

export function isApprovalMode(value: unknown): value is ApprovalMode {
  return value === "ask" || value === "auto" || value === "allow_all";
}

export function approvalLabel(mode: ApprovalMode): string {
  return APPROVAL_MODES.find((m) => m.id === mode)?.label ?? "";
}

/** The dialog shown before "Allow all" is switched on. */
export const ALLOW_ALL_CONFIRM = {
  title: "Allow every tool to run without asking?",
  message:
    "Agents will be able to change your notes, run commands and use any tool you have turned on, without asking you first. You can switch back at any time.",
  confirmLabel: "Allow all",
};
