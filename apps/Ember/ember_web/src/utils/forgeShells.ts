import type { ForgeProvider } from "../api/ForgeClient";

export type ForgeShell = "powershell" | "cmd" | "gitbash";

export const SHELL_OPTIONS = [
  { value: "powershell", label: "PowerShell" },
  { value: "cmd", label: "Command Prompt" },
  { value: "gitbash", label: "Git Bash" },
] as const;

export const DEFAULT_SHELL: ForgeShell = "powershell";
const STORAGE_KEY = "ember_web.forgeShell";

/** The command that pairs a worker. PowerShell does not run a script from the current folder by bare name. */
export function pairCommand(shell: ForgeShell, origin: string, token: string, provider: ForgeProvider): string {
  const launcher = shell === "powershell" ? ".\run.bat" : shell === "gitbash" ? "./run.bat" : "run.bat";
  return `${launcher} pair ${origin} ${token} --provider ${provider}`;
}

// Per-browser convenience: blocked or damaged storage just means the default shell.
export function readShell(): ForgeShell {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return SHELL_OPTIONS.some((o) => o.value === stored) ? (stored as ForgeShell) : DEFAULT_SHELL;
  } catch {
    return DEFAULT_SHELL;
  }
}

export function writeShell(shell: ForgeShell): void {
  try {
    localStorage.setItem(STORAGE_KEY, shell);
  } catch {
    // ignore - see readShell
  }
}
