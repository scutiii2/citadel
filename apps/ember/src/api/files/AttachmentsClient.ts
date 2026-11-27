import { apiRequest } from "../http";
import { AUDIO_FILE } from "../../utils/content/attachments";

/** What mcp_server kept of an attached .csv / .xlsx for the data tools. */
export interface AttachmentTable {
  table_id: string;
  filename: string;
  rows: number;
  columns: string[];
  sheet: string | null;
  notes: string[];
}

/** How a file was read beyond its text preview: by Reader or Scribe, or left to Legion (`pages`, `listen`). */
export type ReadPath = "reader" | "pages" | "scribe" | "listen";

/** One uploaded file. `file_id` is null when it could not be stored and only its text is attached. */
export interface AttachmentFile {
  filename: string;
  file_id: string | null;
  kind: string;
  size: number;
  pages: number | null;
  expires_at: number | null;
  text: string;
  char_count: number;
  truncated: boolean;
  /** The data tools' copy of a .csv / .xlsx, when one was made. */
  table: AttachmentTable | null;
  /** Set for a PDF with no text of its own, and for audio. */
  read: ReadPath | null;
}

interface AttachmentDocument {
  filename: string;
  text: string;
  char_count: number;
  truncated: boolean;
  read: "reader" | "pages";
}

export interface DictationResult {
  text: string;
  duration_s: number;
}

/** Same limit ember_api enforces; checked here first to skip the upload. */
export const MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024;

/** ember_api's limit for audio (base64 must fit its request cap). */
const MAX_AUDIO_BYTES = 20 * 1024 * 1024;

/** The file's bytes as base64 (ember_api takes JSON only). */
export function toBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      resolve(url.slice(url.indexOf(",") + 1)); // drop "data:<type>;base64,"
    };
    reader.onerror = () => reject(reader.error ?? new Error("Could not read the file"));
    reader.readAsDataURL(file);
  });
}

export const attachmentsClient = {
  async dictatePartial(blob: Blob, signal?: AbortSignal): Promise<DictationResult> {
    if (blob.size > MAX_AUDIO_BYTES) throw new Error("Too large - the limit is 20 MB");
    const data = await toBase64(blob);
    signal?.throwIfAborted();
    return apiRequest("POST", "/api/attachments/dictate/partial", {
      filename: "dictation.webm", data,
    }, undefined, signal);
  },
  /** Transcribe a recording into editable draft text through the session API. */
  async dictate(blob: Blob, signal?: AbortSignal): Promise<DictationResult> {
    if (blob.size > MAX_AUDIO_BYTES) throw new Error("Too large - the limit is 20 MB");
    const data = await toBase64(blob);
    signal?.throwIfAborted();
    return apiRequest("POST", "/api/attachments/dictate", {
      filename: "dictation.webm", data,
    }, undefined, signal);
  },
  /** Asks Reader for the text of an image or PDF; `read: "pages"` means it could not. */
  async document(file: File): Promise<AttachmentDocument> {
    if (file.size > MAX_AUDIO_BYTES) throw new Error("Too large - the limit is 20 MB");
    return apiRequest<AttachmentDocument>("POST", "/api/attachments/document", {
      filename: file.name, data: await toBase64(file),
    });
  },
  /** Every file goes up one way: the original is kept and its text comes back. Audio may be larger. */
  async file(file: File): Promise<AttachmentFile> {
    const limit = AUDIO_FILE.test(file.name) ? MAX_AUDIO_BYTES : MAX_ATTACHMENT_BYTES;
    if (file.size > limit) throw new Error(`Too large - the limit is ${limit / (1024 * 1024)} MB`);
    return apiRequest<AttachmentFile>("POST", "/api/attachments/file", {
      filename: file.name,
      data: await toBase64(file),
    });
  },
};
