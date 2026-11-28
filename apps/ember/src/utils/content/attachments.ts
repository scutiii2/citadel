/** Attached files travel inside the question text, one delimited block per
 * file after what was typed - the same markers chat_app writes, so the
 * agent sees the same thing and saved chats render the same in both apps.
 * The chat view pulls the blocks back out to show them collapsed. */

import type { AttachmentFile, AttachmentTable, ReadPath } from "../../api/files/AttachmentsClient";
import type { ChatMessage } from "../../api/types";

export interface AttachmentBlock {
  filename: string;
  chars: number;
  truncated: boolean;
  text: string;
}

const BLOCK = /\[\[ATTACHMENT filename="([^"]*)" chars="(\d+)" truncated="(true|false)"\]\]\n([\s\S]*?)\n\[\[\/ATTACHMENT\]\]/g;

function attachmentBlock(a: AttachmentBlock): string {
  const name = a.filename.replace(/"/g, "'");
  return `[[ATTACHMENT filename="${name}" chars="${a.chars}" truncated="${a.truncated}"]]\n${a.text}\n[[/ATTACHMENT]]`;
}

/** What stands in for the typed text when a question is only attached files. */
export const FILE_ONLY_QUESTION = "Please review the attached file(s).";

/** Files whose whole content the agent's data tools can read. */
export const TABLE_FILE = /\.(csv|xlsx)$/i;

/** Audio files, which may be larger than other attachments. */
export const AUDIO_FILE = /\.(mp3|wav|m4a|ogg|flac|webm)$/i;

/** Images and PDFs Reader can read (it reads fewer formats than the file store keeps). */
export const DOCUMENT_FILE = /\.(pdf|png|jpe?g|webp)$/i;

/** How many PDF pages Legion shows the model per turn (its `images.MAX_PAGES`). */
export const MAX_SCAN_PAGES = 10;

const MAX_LISTED_COLUMNS = 30;

/** The line that opens an attachment's text for a table: the id the data tools
 * need, the size, the columns, and a warning that the text below is only a
 * preview. Column names are flattened to one line so one can never close the
 * attachment block. `null` means the upload failed: only the preview exists. */
export function tableHeader(table: AttachmentTable | null): string {
  if (!table) return "[The whole file could not be loaded for analysis, so only the preview below is available.]\n";
  const names = table.columns.slice(0, MAX_LISTED_COLUMNS).map((name) => name.replace(/\s+/g, " "));
  const more = table.columns.length > MAX_LISTED_COLUMNS ? ", ..." : "";
  return `[table_id: ${table.table_id} | ${table.rows} rows | columns: ${names.join(", ")}${more} | the text below is only a preview of the start of the file; use the data tools with this table_id for the whole file]\n`;
}

/** The stored image an attachment's first line names, current and older saved forms. */
export function imageFileId(text: string): string | undefined {
  const found = text.match(
    /^\[(?:File file_id: ([A-Za-z0-9_-]{1,100}) \| image(?: \||\])|(?:Image|PDFMerger) file_id: ([A-Za-z0-9_-]{1,100}) \| \d+ pages \| image(?: \||\]))/,
  );
  return found?.[1] ?? found?.[2];
}

/** Whether the server has dropped the file an attachment's first line names. */
export function isExpired(text: string, now: number = Date.now()): boolean {
  const found = text.match(/^\[(?:File|Image|PDFMerger) file_id: [^\]\n]*\| expires_at: (\d+(?:\.\d+)?)/);
  return found !== null && Number(found[1]) * 1000 <= now;
}

/** What asks Legion to read a file itself: show a PDF's pages, or transcribe audio. */
const LEGION_MARKS: Partial<Record<ReadPath, string>> = { pages: " | scan", listen: " | listen" };

/** The first line of a stored attachment: the id the file tools need and what the file is. */
export function fileHeader(f: {
  file_id: string | null; kind: string; pages: number | null; expires_at: number | null; read?: ReadPath | null;
}): string {
  const pages = f.pages ? ` | ${f.pages} pages` : "";
  const mark = f.read ? (LEGION_MARKS[f.read] ?? "") : "";
  return `[File file_id: ${f.file_id} | ${f.kind}${pages}${mark} | expires_at: ${f.expires_at} | preserve this file_id when delegating]`;
}

function noPreview(file: AttachmentFile): string {
  if (file.read === "pages") return "[No text layer; this PDF's pages are shown to the model as images.]";
  if (file.read === "listen") return "[No transcript yet; the audio is transcribed when the question is sent.]";
  if (file.kind === "image") return "[No text preview available; inspect the original image when needed.]";
  return "[No text preview available; the original file is available for inspection.]";
}

/** What one uploaded file puts into the question: its id line, the table line, then the preview. */
export function fileText(file: AttachmentFile): string {
  const id = file.file_id ? `${fileHeader(file)}\n` : "";
  const table = TABLE_FILE.test(file.filename) ? tableHeader(file.table) : "";
  return id + table + (file.text || noPreview(file));
}

/** A stored PDF's attachment text with `scan` added to its id line. */
export function markScan(text: string): string {
  return text.replace(/^(\[File file_id: [^|\]]+ \| pdf \| \d+ pages) \| (?!scan)/, "$1 | scan | ");
}

/** Attachment text with everything under the id line replaced by what Reader read. */
export function withReadText(text: string, read: string): string {
  return text.startsWith("[File file_id: ") ? `${text.slice(0, text.indexOf("\n"))}\n${read}` : read;
}

/** The question as sent: the typed text, then every attachment. */
export function withAttachments(question: string, attachments: AttachmentBlock[]): string {
  if (!attachments.length) return question;
  const typed = question || FILE_ONLY_QUESTION;
  return [typed, ...attachments.map(attachmentBlock)].join("\n\n");
}

/** Splits a saved question back into what was typed and its attachments. */
export function splitAttachments(text: string): { text: string; attachments: AttachmentBlock[] } {
  if (!text.includes("[[ATTACHMENT ")) return { text, attachments: [] };
  const attachments: AttachmentBlock[] = [];
  const rest = text.replace(BLOCK, (_m, filename: string, chars: string, truncated: string, body: string) => {
    attachments.push({ filename, chars: Number(chars), truncated: truncated === "true", text: body });
    return "";
  });
  return { text: rest.trim(), attachments };
}

/** What the user typed in a chat, oldest first, for the input's up and down
 * arrows: questions and slash commands, without their attached files. */
export function questionHistory(messages: ChatMessage[]): string[] {
  return messages
    .filter((m) => m.role === "user" && m.kind !== "summary" && m.kind !== "log_attachment")
    .map((m) => splitAttachments(m.content).text)
    .filter((text) => text !== "");
}
