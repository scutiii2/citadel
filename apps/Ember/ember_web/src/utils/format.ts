const KB = 1024;
const MB = KB * 1024;
const GB = MB * 1024;

/** "512 B", "2 KB", "5.0 MB", "3.00 GB". A part of a KB rounds up, so a small file never reads "0 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < KB) return `${bytes} B`;
  if (bytes < MB) return `${Math.ceil(bytes / KB)} KB`;
  if (bytes < GB) return `${(bytes / MB).toFixed(1)} MB`;
  return `${(bytes / GB).toFixed(2)} GB`;
}

/** "1 file", "2 files". */
export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** 5 -> "05". */
export function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** A Markdown table cell must not contain the column separator or a line break. */
export function markdownCell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}
