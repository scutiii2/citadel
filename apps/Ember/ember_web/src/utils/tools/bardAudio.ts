import type { ToolStep } from "../../api/types";

// Matched by suffix: an extension's tools arrive namespaced (`bard__tool_bard_speak`).
const SPEAK_TOOL = "tool_bard_speak";

export interface BardClip {
  fileId: string;
  voice: string;
  durationS: number | null;
}

/** The audio Bard produced in these steps, in order and without repeats. */
export function bardClips(steps: readonly ToolStep[] | undefined): BardClip[] {
  const clips: BardClip[] = [];
  for (const step of steps ?? []) {
    if (step.ok !== true || !step.tool.endsWith(SPEAK_TOOL)) continue;
    try {
      const result = JSON.parse(step.result) as { file_id?: unknown; voice?: unknown; duration_s?: unknown };
      if (typeof result.file_id !== "string" || clips.some((c) => c.fileId === result.file_id)) continue;
      clips.push({
        fileId: result.file_id,
        voice: typeof result.voice === "string" ? result.voice : "",
        durationS: typeof result.duration_s === "number" && Number.isFinite(result.duration_s) ? result.duration_s : null,
      });
    } catch {
      // Not JSON: nothing to play.
    }
  }
  return clips;
}
