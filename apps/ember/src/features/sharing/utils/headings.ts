const HEADING = /^(#{1,6})[ \t]+([^\n]+?)[ \t#]*(?![\s\S])/;
const WHITESPACE = /[\p{White_Space}\u001c-\u001f]+/u;
const FENCE = /^(`{3,}|~{3,})([^\n]*)/;

/** The headings of a Markdown text that can be shared as a section, in order: the first of each (the server cuts the
 * section at the first heading that matches, ignoring case and spacing). Same rules as `extract_section` in
 * apps/stronghold/src/brain/fragments.py: `#` to `######` and a space, outside fenced code. */
export function headingsOf(body: string): string[] {
  const seen = new Set<string>();
  const found: string[] = [];
  let fence = "";
  for (const line of body.split("\n")) {
    const marker = FENCE.exec(line.replace(/^[\p{White_Space}\u001c-\u001f]+/u, ""));
    if (fence) {
      if (marker && marker[1]![0] === fence[0] && marker[1]!.length >= fence.length && marker[2]!.split(WHITESPACE).every((part) => !part)) fence = "";
      continue;
    }
    if (marker) {
      fence = marker[1]!;
      continue;
    }
    const heading = HEADING.exec(line);
    if (!heading) continue;
    const text = heading[2]!.split(WHITESPACE).filter(Boolean).join(" ");
    const key = text.toLowerCase();
    if (text && [...text].length <= 200 && !seen.has(key)) {
      seen.add(key);
      found.push(text);
    }
  }
  return found;
}
