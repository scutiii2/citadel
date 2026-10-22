import { computed, ref } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { attachmentsClient } from "../../../api/files/AttachmentsClient";
import { splitAttachments, PDF_FILE, TABLE_FILE, tableHeader } from "../../../utils/content/attachments";
import { errorMessage } from "../../../utils/errors";

/** File uploads, previews, and input events for one chat composer. */
export function useComposerAttachments() {
  const auth = useAuthStore();
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
      if (PDF_FILE.test(file.name)) {
        void attachmentsClient.pdf(file).then((result) => {
          const image = result.kind === "image";
          Object.assign(live, {
            state: "ready",
            text: image
              ? `[Image file_id: ${result.file_id} | ${result.pages} pages | image | expires_at: ${result.expires_at} | preserve this file_id when delegating; the original image is stored with the pdf_merger tools]\n[No text preview available; inspect the original image when needed.]`
              : `[PDFMerger file_id: ${result.file_id} | ${result.pages} pages | ${result.kind} | expires_at: ${result.expires_at} | use pdf_merger tools to inspect/merge this original; preserve this file_id when delegating to PDF Assistant]\n` +
                (result.text || "[No text preview available; the original file is available for inspection and merging.]"),
            chars: result.char_count, truncated: result.truncated, pages: result.pages,
          });
        }).catch((err: unknown) => Object.assign(live, { state: "error", error: errorMessage(err) }));
        continue;
      }
      // A .csv / .xlsx is also uploaded whole, so the data tools can read every
      // row; the text preview stays as the fallback if that upload fails.
      const wantsTable = TABLE_FILE.test(file.name);
      const tableUpload = wantsTable ? attachmentsClient.table(file).catch(() => null) : Promise.resolve(null);
      // Each file on its own: one slow or broken file doesn't hold up the rest.
      void Promise.all([attachmentsClient.text(file), tableUpload])
        .then(([result, uploaded]) => {
          Object.assign(live, {
            state: "ready",
            text: (wantsTable ? tableHeader(uploaded) : "") + result.text,
            chars: result.char_count,
            truncated: result.truncated,
            rows: uploaded?.rows ?? 0,
            columns: uploaded?.columns.length ?? 0,
          });
        })
        .catch((err: unknown) => {
          Object.assign(live, { state: "error", error: errorMessage(err) });
        });
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
    removeAttachment, restoreAttachments, onPick, onDragOver, onDragLeave, onDrop, onPaste,
  };
}
