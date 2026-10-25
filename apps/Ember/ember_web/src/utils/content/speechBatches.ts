import MarkdownIt from "markdown-it";

// Parse only: no generated HTML is inserted into the document.
const markdown = new MarkdownIt({ html: true });

/** Plain spoken prose, omitting fenced/indented code and HTML blocks. */
function spokenText(source: string): string {
  return markdown.parse(source, {}).filter((token) => token.type === "inline").map((token) =>
    (token.children ?? []).map((child) => {
      if (child.type === "text" || child.type === "code_inline") return child.content;
      if (child.type === "softbreak" || child.type === "hardbreak") return " ";
      return "";
    }).join(""),
  ).join(" ").replace(/\s+/g, " ").trim();
}

/** Keep common English abbreviations together while preferring sentence boundaries. */
function sentences(text: string): string[] {
  const result: string[] = [];
  let start = 0;
  for (const match of text.matchAll(/[.!?]+["'”’)]*(?=\s|$)/g)) {
    const end = match.index + match[0].length;
    const part = text.slice(start, end);
    if (/(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc)|\b(?:e\.g|i\.e)|\b[A-Z]|\b(?:[A-Za-z]\.)+[A-Za-z])\.$/i.test(part)) continue;
    result.push(part.trim());
    start = end;
  }
  const rest = text.slice(start).trim();
  if (rest) result.push(rest);
  return result;
}

/** Batch cleaned sentences below Bard's 5,000-character limit with ample headroom. */
export function speechBatches(source: string, limit = 3500): string[] {
  if (!Number.isInteger(limit) || limit < 1) throw new RangeError("Batch size must be positive");
  const batches: string[] = [];
  let current = "";
  for (const sentence of sentences(spokenText(source))) {
    let rest = sentence;
    if (current && current.length + rest.length + 1 > limit) {
      batches.push(current);
      current = "";
    }
    while (rest.length > limit) {
      const space = rest.lastIndexOf(" ", limit);
      const split = space > 0 ? space : limit;
      batches.push(rest.slice(0, split));
      rest = rest.slice(split).trimStart();
    }
    if (rest) current = current ? `${current} ${rest}` : rest;
  }
  if (current) batches.push(current);
  return batches;
}
