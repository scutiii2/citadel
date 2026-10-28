import { apiRequest } from "../http";

export interface AttachmentText {
  filename: string;
  text: string;
  char_count: number;
  truncated: boolean;
}

/** What mcp_server kept of an attached .csv / .xlsx for the data tools. */
export interface AttachmentTable {
  table_id: string;
  filename: string;
  rows: number;
  columns: string[];
  sheet: string | null;
  notes: string[];
}

export interface AttachmentPdf extends AttachmentText {
  file_id: string;
  pages: number;
  kind: string;
  expires_at: number;
}

export interface AttachmentAudio {
  filename: string;
  file_id: string;
  duration_s: number;
  expires_at: number;
}

export interface DictationResult {
  text: string;
  duration_s: number;
}

/** Same limit ember_api enforces; checked here first to skip the upload. */
export const MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024;

/** ember_api's limit for audio (base64 must fit its request cap). */
export const MAX_AUDIO_BYTES = 20 * 1024 * 1024;

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
  async pdf(file: File): Promise<AttachmentPdf> {
    if (file.size > MAX_ATTACHMENT_BYTES) throw new Error("Too large - the limit is 15 MB");
    return apiRequest<AttachmentPdf>("POST", "/api/attachments/pdf", {
      filename: file.name, data: await toBase64(file),
    });
  },
  /** Text ember_api extracted from the file; the file itself isn't kept. */
  async text(file: File): Promise<AttachmentText> {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      throw new Error(`Too large - the limit is ${MAX_ATTACHMENT_BYTES / (1024 * 1024)} MB`);
    }
    return apiRequest<AttachmentText>("POST", "/api/attachments/text", {
      filename: file.name,
      data: await toBase64(file),
    });
  },

  /** Uploads the whole file so the agent's data tools can read every row. */
  async table(file: File): Promise<AttachmentTable> {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      throw new Error(`Too large - the limit is ${MAX_ATTACHMENT_BYTES / (1024 * 1024)} MB`);
    }
    return apiRequest<AttachmentTable>("POST", "/api/attachments/table", {
      filename: file.name,
      data: await toBase64(file),
    });
  },
};
