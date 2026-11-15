/** True when every whitespace-separated word of `query` appears in `fields`
 * (case-insensitive). An empty query matches everything. */
export function matchesWords(query: string, ...fields: string[]): boolean {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const text = fields.join(" ").toLocaleLowerCase();
  return words.every((word) => text.includes(word));
}
