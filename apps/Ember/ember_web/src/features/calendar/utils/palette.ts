/** Default colors offered to a new calendar (user data, so literal values are fine here). No green: event cells are green. */
export const FEED_COLORS: readonly string[] = ["#2563eb", "#dc2626", "#d97706", "#7c3aed", "#0891b2", "#db2777"];

export function nextFeedColor(used: readonly string[]): string {
  return FEED_COLORS.find((color) => !used.includes(color)) ?? FEED_COLORS[used.length % FEED_COLORS.length]!;
}
