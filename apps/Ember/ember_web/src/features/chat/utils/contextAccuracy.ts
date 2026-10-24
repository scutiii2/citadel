/** How the context breakdown is counted. The chat settings menu and the Settings page share these. */

export type ContextAccuracy = "estimate" | "exact";

export const CONTEXT_ACCURACY_OPTIONS: readonly { value: ContextAccuracy; label: string }[] = [
  { value: "estimate", label: "Estimate" },
  { value: "exact", label: "Exact" },
];

/** Estimate is free; exact asks the provider to count and so costs extra requests. */
export const DEFAULT_CONTEXT_ACCURACY: ContextAccuracy = "estimate";

export function isContextAccuracy(value: unknown): value is ContextAccuracy {
  return value === "estimate" || value === "exact";
}
