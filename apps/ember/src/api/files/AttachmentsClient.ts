import { apiRequest } from "../http";

/** What mcp_server kept of an attached .csv / .xlsx for the data tools. */
export interface AttachmentTable {
  table_id: string;
  filename: string;
  rows: number;
  columns: string[];
  sheet: string | null;
  notes: string[];
}

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
}

interface AttachmentAudio {
  filename: string;
  file_id: string;
  duration_s: number;
  expires_at: number;
}

interface AttachmentDocument {
  filename: string;
  file_id: string;
  page_count: number;
  expires_at: number;
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
  /** Uploads the audio to Scribe through ember_api; the agent transcribes it by file_id. */
  async audio(file: File): Promise<AttachmentAudio> {
    if (file.size > MAX_AUDIO_BYTES) throw new Error("Too large - the limit is 20 MB");
    return apiRequest<AttachmentAudio>("POST", "/api/attachments/audio", {
      filename: file.name, data: await toBase64(file),
    });
  },
  /** Uploads the document to Reader through ember_api; the agent reads it with tool_ocr_parse by file_id. */
  async document(file: File): Promise<AttachmentDocument> {
    if (file.size > MAX_AUDIO_BYTES) throw new Error("Too large - the limit is 20 MB");
    return apiRequest<AttachmentDocument>("POST", "/api/attachments/document", {
      filename: file.name, data: await toBase64(file),
    });
  },
  /** Every file but audio goes up one way: the original is kept and a text preview comes back. */
  async file(file: File): Promise<AttachmentFile> {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      throw new Error(`Too large - the limit is ${MAX_ATTACHMENT_BYTES / (1024 * 1024)} MB`);
    }
    return apiRequest<AttachmentFile>("POST", "/api/attachments/file", {
      filename: file.name,
      data: await toBase64(file),
    });
  },
};
