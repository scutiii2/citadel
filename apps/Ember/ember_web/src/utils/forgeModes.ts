import type { ForgeMode } from "../api/ForgeClient";

export const MODE_OPTIONS: readonly { value: ForgeMode; label: string }[] = [
  { value: "ask", label: "Ask" },
  { value: "accept_edits", label: "Accept edits" },
  { value: "plan", label: "Plan" },
  { value: "full_auto", label: "Full auto" },
];

/** A new group can start in any mode except full auto, which is switched on afterwards with a confirmation. */
export const CREATE_MODE_OPTIONS = MODE_OPTIONS.filter((option) => option.value !== "full_auto");

export const MODE_HELP: Record<ForgeMode, string> = {
  ask: "Claude asks you before it edits files or runs commands. Codex cannot ask, so it only reads.",
  accept_edits: "Edits go through without asking. Claude still asks before running commands. Codex may change files in the folder.",
  plan: "Workers read and plan but change nothing.",
  full_auto: "Workers run any tool without asking. Use only in a folder you can afford to lose.",
};

/** Typed to confirm switching a group to full auto. */
export const FULL_AUTO_PHRASE = "full auto";
