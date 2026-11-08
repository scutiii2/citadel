const NAME = "read-aloud";
const SKIP = "pre, code, button, time, .actions, details, [aria-hidden='true']";

interface Word { node: Text; start: number; end: number }

/** Relative speaking time of a word: its letters plus the pause a following punctuation mark adds. */
const weight = (word: string) => word.length + 1 + (/[.!?…]["'”’)]*$/.test(word) ? 5 : /[,;:—–]$/.test(word) ? 2 : 0);

const norm = (word: string) => word.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");

/** Visible prose words under `root`; code blocks and controls are never spoken. */
function pageWords(root: HTMLElement): Word[] {
  const words: Word[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => node.parentElement?.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    for (const m of (node as Text).data.matchAll(/\S+/g)) {
      words.push({ node: node as Text, start: m.index, end: m.index + m[0].length });
    }
  }
  return words;
}

/**
 * Highlights the word being spoken. Bard returns no word timings, so the word is estimated from how far
 * through a batch's audio playback is, weighted by character count; spoken words are matched to page words
 * in order, since markdown syntax and code make the two lists differ.
 */
export function createSpeechHighlight() {
  let batchWords: string[][] = [];
  let pageMap: Word[] = [];
  let spokenToPage: number[] = [];
  let offsets: number[] = [];
  let last = -1;
  const supported = typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight !== "undefined";

  function begin(root: HTMLElement | null, batches: string[]): void {
    clear();
    if (!supported || !root) return;
    batchWords = batches.map((b) => b.split(/\s+/).filter(Boolean));
    offsets = [];
    let count = 0;
    for (const words of batchWords) { offsets.push(count); count += words.length; }
    pageMap = pageWords(root);
    const pageNorm = pageMap.map((w) => norm(w.node.data.slice(w.start, w.end)));
    let cursor = 0;
    spokenToPage = batchWords.flat().map((word) => {
      const key = norm(word);
      if (!key) return Math.max(0, cursor - 1);
      for (let j = cursor; j < Math.min(pageNorm.length, cursor + 30); j++) {
        if (pageNorm[j] === key) { cursor = j + 1; return j; }
      }
      return Math.max(0, cursor - 1);
    });
  }

  function update(position: { batch: number; fraction: number } | null): void {
    const words = position && batchWords[position.batch];
    if (!supported || !position || !words?.length) return;
    const total = words.reduce((sum, w) => sum + weight(w), 0);
    let seen = 0;
    let local = 0;
    while (local < words.length - 1 && seen + weight(words[local]!) <= position.fraction * total) {
      seen += weight(words[local]!);
      local++;
    }
    const target = pageMap[spokenToPage[offsets[position.batch]! + local]!];
    if (!target || spokenToPage[offsets[position.batch]! + local] === last) return;
    last = spokenToPage[offsets[position.batch]! + local]!;
    const range = new Range();
    range.setStart(target.node, target.start);
    range.setEnd(target.node, target.end);
    CSS.highlights.set(NAME, new Highlight(range));
    follow(range);
  }

  /** Scroll only when the word leaves the comfortable middle of the view, so reading stays steady. */
  function follow(range: Range): void {
    const box = range.getBoundingClientRect();
    if (box.top < 96 || box.bottom > window.innerHeight - 140) {
      range.startContainer.parentElement?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  function clear(): void {
    last = -1;
    batchWords = []; pageMap = []; spokenToPage = []; offsets = [];
    if (supported) CSS.highlights.delete(NAME);
  }

  return { begin, update, clear };
}
