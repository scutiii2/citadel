/** What each chat setting costs in model tokens, shown beside the setting.
 *
 * Rough figures (about four characters per token), measured from the prompt
 * text ai_agent sends: the update_plan tool definition is about 200 tokens, the
 * "update only on change" sentence about 35, the terse-reply rule about 120.
 * Re-check them when those prompts change. */
export type CostedSetting =
  | "terse"
  | "plan"
  | "planLean"
  | "askTools"
  | "chime"
  | "notifications"
  | "suggestions"
  | "liveTokens"
  | "contextPanel"
  | "contextAccuracy";

export const TOKEN_COSTS: Record<CostedSetting, string> = {
  terse:
    "Adds about 120 input tokens to every model call, but shorter answers usually save more output tokens than that.",
  plan:
    "Adds about 200 input tokens to every model call, plus about 15-25 output tokens per item each time the agent updates the list (roughly 400-500 for a 5-step task). Off costs nothing.",
  planLean:
    "Adds about 35 input tokens per call. Saves roughly 100-150 output tokens, plus a model round, for each unneeded update it avoids.",
  askTools: "No token cost. It only waits for you.",
  chime: "No token cost. It runs in your browser.",
  notifications: "No token cost. It runs in your browser.",
  suggestions:
    "One extra small model call per answer: about 300-1000 input tokens and about 20 output tokens. Cached per answer.",
  liveTokens: "No token cost. It only shows a count the agent already reports.",
  contextPanel: "No token cost with Estimate. Exact adds token-count requests, see its own setting.",
  contextAccuracy:
    "Estimate costs no tokens. Exact asks the provider to count each part, which adds requests (no model output) each time the panel opens; results are cached.",
};

/** A tooltip: the setting's own hint, then its token cost. */
export function withTokenCost(hint: string, setting: CostedSetting): string {
  return `${hint}. ${TOKEN_COSTS[setting]}`;
}
