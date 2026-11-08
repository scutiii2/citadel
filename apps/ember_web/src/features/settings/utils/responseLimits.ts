import type { AccountLimits, Limits } from "../../../api/navigation/TuningClient";

/** Owned by Settings so filtering a group never destroys its account draft. */
export interface ResponseLimitsState {
  stored: AccountLimits | null;
  draft: Record<keyof Limits, string>;
  pending: boolean;
}
export const emptyLimitsState = (): ResponseLimitsState => ({ stored: null, draft: { max_output_tokens: "", max_tool_rounds: "" }, pending: false });
export function adoptLimits(value: AccountLimits): ResponseLimitsState {
  return { stored: value, draft: { max_output_tokens: value.limits.max_output_tokens === null ? "" : String(value.limits.max_output_tokens), max_tool_rounds: value.limits.max_tool_rounds === null ? "" : String(value.limits.max_tool_rounds) }, pending: false };
}
export function limitsDirty(state: ResponseLimitsState): boolean {
  return state.stored !== null && (Object.keys(state.draft) as (keyof Limits)[]).some(key => state.draft[key] !== (state.stored!.limits[key] === null ? "" : String(state.stored!.limits[key])));
}
export function limitsPayload(draft: ResponseLimitsState["draft"]): Limits {
  return { max_output_tokens: draft.max_output_tokens === "" ? null : Number(draft.max_output_tokens), max_tool_rounds: draft.max_tool_rounds === "" ? null : Number(draft.max_tool_rounds) };
}
