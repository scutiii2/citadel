import { computed, ref } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { useToolConnectionsStore } from "../../../stores/toolConnections";
import { attachmentsClient } from "../../../api/files/AttachmentsClient";
import { splitAttachments, AUDIO_FILE, DOCUMENT_FILE, audioHeader, documentHeader, fileText } from "../../../utils/content/attachments";
import { errorMessage } from "../../../utils/errors";

/** File uploads, previews, and input events for one chat composer. */
export function useComposerAttachments() {
  const auth = useAuthStore();
  const connections = useToolConnectionsStore();
  const dragging = ref(false);
  /** A file attached to the next question. Its text is extracted by ember_api
   * as soon as it's added, so sending doesn't wait for an upload. */
  interface PendingAttachment {
    id: number;
    filename: string;
    state: "reading" | "ready" | "error";
    text: string;
    chars: number;
    truncated: boolean;
    /** Rows and columns of the table mcp_server kept (0 for any other file). */
    rows: number;
    columns: number;
    error: string;
    pages?: number;
    /** The original file, kept only while Reader (OCR) can still be asked to read it. */
    source?: File;
    ocr?: "reading" | "done" | "error";
  }

  let nextAttachmentId = 1;
  const attachments = ref<PendingAttachment[]>([]);
  const reading = computed(() => attachments.value.some((a) => a.state === "reading"));
  const ready = computed(() => attachments.value.filter((a) => a.state === "ready"));
  async function addFiles(files: FileList | File[] | null | undefined): Promise<void> {
    if (!auth.hasPermission("files.upload")) return;
    for (const file of Array.from(files ?? [])) {
      const entry: PendingAttachment = {
        id: nextAttachmentId++,
        filename: file.name,
        state: "reading",
        text: "",
        chars: 0,
        truncated: false,
        rows: 0,
        columns: 0,
        error: "",
      };
      attachments.value.push(entry);
      const live = attachments.value[attachments.value.length - 1]!; // the reactive copy
      if (AUDIO_FILE.test(file.name)) {
        const reason = connections.reason("scribe");
        if (reason) {
          Object.assign(live, { state: "error", error: reason });
          continue;
        }
        void attachmentsClient.audio(file).then((result) => {
          const text = audioHeader(result);
          Object.assign(live, { state: "ready", text, chars: text.length });
        }).catch((err: unknown) => Object.assign(live, { state: "error", error: errorMessage(err) }));
        continue;
      }
      // Every other file goes up the same way. Each on its own: one slow or broken file doesn't hold up the rest.
      void attachmentsClient.file(file).then((result) => {
        const text = fileText(result);
        Object.assign(live, {
          state: "ready",
          text,
          chars: result.char_count,
          truncated: result.truncated,
          rows: result.table?.rows ?? 0,
          columns: result.table?.columns.length ?? 0,
          pages: result.pages ?? undefined,
          // Reader (OCR) is opt-in: the file is kept so "Read with OCR" can upload it on request.
          source: DOCUMENT_FILE.test(file.name) ? file : undefined,
        });
      }).catch((err: unknown) => Object.assign(live, { state: "error", error: errorMessage(err) }));
    }
  }

  /** Only on the user's request: upload the kept original to Reader and tell the agent to OCR it. */
  async function readWithOcr(id: number): Promise<void> {
    const live = attachments.value.find((a) => a.id === id);
    if (!live?.source || live.ocr === "reading" || live.ocr === "done") return;
    live.ocr = "reading";
    try {
      const doc = await attachmentsClient.document(live.source);
      live.text = documentHeader(doc) + "\n" + live.text;
      live.chars = live.text.length;
      live.ocr = "done";
    } catch (err: unknown) {
      live.ocr = "error";
      live.error = errorMessage(err);
    }
  }

  function removeAttachment(id: number): void {
    attachments.value = attachments.value.filter((a) => a.id !== id);
  }

  function onPick(event: Event): void {
    const input = event.target as HTMLInputElement;
    void addFiles(input.files);
    input.value = ""; // picking the same file again still fires change
  }

  function hasFiles(event: DragEvent): boolean {
    return event.dataTransfer?.types.includes("Files") ?? false;
  }

  // The whole composer is the drop target (suggestions and chips included),
  // but dragged text or links are left to the browser.
  function onDragOver(event: DragEvent): void {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragging.value = true;
  }

  function onDragLeave(event: DragEvent): void {
    // Moving over a child element also fires dragleave on the form.
    if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) dragging.value = false;
  }

  function onDrop(event: DragEvent): void {
    dragging.value = false;
    if (!hasFiles(event)) return;
    event.preventDefault();
    void addFiles(event.dataTransfer?.files);
  }

  /** Pasted files (a screenshot, a file copied in the explorer) become
   * attachments. Pasted text - even with an accompanying image, as copying
   * spreadsheet cells does - pastes as usual. */
  function onPaste(event: ClipboardEvent): void {
    const data = event.clipboardData;
    if (!data?.files.length || data.getData("text/plain")) return;
    event.preventDefault();
    void addFiles(data.files);
  }

  function restoreAttachments(question: string): string {
    const { text, attachments: files } = splitAttachments(question);
    for (const file of files) {
      attachments.value.push({ id: nextAttachmentId++, filename: file.filename, state: "ready", text: file.text, chars: file.chars, truncated: file.truncated, rows: 0, columns: 0, error: "" });
    }
    return text;
  }

  return {
    attachments, reading, ready, dragging,
    removeAttachment, readWithOcr, restoreAttachments, onPick, onDragOver, onDragLeave, onDrop, onPaste,
  };
}
