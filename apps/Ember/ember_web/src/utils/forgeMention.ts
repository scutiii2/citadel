/** Helpers for the composer's @mention menu. */

export interface MentionQuery {
  /** Index of the "@". */
  start: number;
  /** What was typed after it. */
  query: string;
}

const TYPING = /(?:^|\s)@([A-Za-z0-9_-]{0,24})$/;

/** The @mention being typed right before `caret`, or null. */
export function mentionAt(text: string, caret: number): MentionQuery | null {
  const match = TYPING.exec(text.slice(0, caret));
  if (!match) return null;
  const query = match[1]!;
  return { start: caret - query.length - 1, query };
}

export function matchingLabels(labels: string[], query: string): string[] {
  const wanted = query.toLowerCase();
  return labels.filter((label) => label.toLowerCase().startsWith(wanted));
}

/** Writes `@label ` in place of the typed `@query`; the caret lands after the space. */
export function completeMention(
  text: string,
  mention: MentionQuery,
  caret: number,
  label: string,
): { text: string; caret: number } {
  const inserted = `@${label} `;
  return { text: text.slice(0, mention.start) + inserted + text.slice(caret), caret: mention.start + inserted.length };
}
