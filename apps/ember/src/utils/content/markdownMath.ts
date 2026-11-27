import katex from "katex";
import type MarkdownIt from "markdown-it";

type Parser = InstanceType<typeof MarkdownIt>;

// A single "$" is left out on purpose: in a chat reply it is far more often a price than a formula.
const DELIMITERS = [
  { open: "\\[", close: "\\]", display: true },
  { open: "$$", close: "$$", display: true },
  { open: "\\(", close: "\\)", display: false },
] as const;

/** The first `close` at or after `from` that is not itself escaped, or -1. */
function closing(source: string, close: string, from: number): number {
  for (let at = source.indexOf(close, from); at !== -1; at = source.indexOf(close, at + 1)) {
    let backslashes = 0;
    while (source[at - 1 - backslashes] === "\\") backslashes += 1;
    if (backslashes % 2 === 0) return at;
  }
  return -1;
}

/** One formula as HTML. The source comes from a model, so KaTeX runs untrusted and size-limited. */
function typeset(md: Parser, source: string, display: boolean): string {
  try {
    const html = katex.renderToString(source, {
      displayMode: display, throwOnError: false, trust: false, strict: "ignore", maxSize: 20,
      errorColor: "var(--danger)",
    });
    // A wide formula scrolls inside its own box, which the keyboard can reach.
    return display ? `<span class="math-block" tabindex="0">${html}</span>` : html;
  } catch {
    return md.utils.escapeHtml(source);
  }
}

/** Typesets \( \), \[ \] and $$ $$. An unfinished formula, as in a streaming reply, stays text. */
export function markdownMath(md: Parser): void {
  // Display math on its own lines, before Markdown can read its "_", "*" or "|" as formatting.
  md.block.ruler.before("fence", "math_block", (state, startLine, endLine, silent) => {
    if (state.sCount[startLine]! - state.blkIndent >= 4) return false;
    const start = state.bMarks[startLine]! + state.tShift[startLine]!;
    const found = DELIMITERS.find((d) => d.display && state.src.startsWith(d.open, start));
    if (!found) return false;
    let line = startLine;
    let end = -1;
    let from = start + found.open.length;
    for (; line < endLine; line += 1) {
      const lineEnd = state.eMarks[line]!;
      const at = closing(state.src.slice(0, lineEnd), found.close, from);
      if (at !== -1) {
        // Text after the closing mark: this is a paragraph, which the inline rule handles.
        if (state.src.slice(at + found.close.length, lineEnd).trim()) return false;
        end = at;
        break;
      }
      from = lineEnd;
    }
    if (end === -1) return false;
    if (silent) return true;
    const token = state.push("math_block", "math", 0);
    token.content = state.src.slice(start + found.open.length, end).trim();
    token.map = [startLine, line + 1];
    state.line = line + 1;
    return true;
  }, { alt: ["paragraph", "reference", "blockquote", "list"] });

  md.inline.ruler.before("escape", "math_inline", (state, silent) => {
    const found = DELIMITERS.find((d) => state.src.startsWith(d.open, state.pos));
    if (!found) return false;
    const from = state.pos + found.open.length;
    const end = closing(state.src.slice(0, state.posMax), found.close, from);
    if (end === -1 || !state.src.slice(from, end).trim()) return false;
    if (!silent) {
      const token = state.push("math_inline", "math", 0);
      token.content = state.src.slice(from, end).trim();
      token.meta = { display: found.display };
    }
    state.pos = end + found.close.length;
    return true;
  });

  md.renderer.rules.math_block = (tokens, idx) => `${typeset(md, tokens[idx]!.content, true)}\n`;
  md.renderer.rules.math_inline = (tokens, idx) =>
    typeset(md, tokens[idx]!.content, (tokens[idx]!.meta as { display: boolean }).display);
}
