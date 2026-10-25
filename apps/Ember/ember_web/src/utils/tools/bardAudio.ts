import type { ToolStep } from "../../api/types";

// Matched by suffix: an extension's tools arrive namespaced (`bard__tool_bard_speak`).
const SPEAK_TOOL = "tool_bard_speak";

/** File ids of the audio Bard produced in these steps, in order and without repeats. */
export function bardFileIds(steps: readonly ToolStep[] | undefined): string[] {
  const ids: string[] = [];
  for (const step of steps ?? []) {
    if (step.ok !== true || !step.tool.endsWith(SPEAK_TOOL)) continue;
    try {
      const id = (JSON.parse(step.result) as { file_id?: unknown }).file_id;
      if (typeof id === "string" && !ids.includes(id)) ids.push(id);
    } catch {
      // Not JSON: nothing to play.
    }
  }
  return ids;
}
