import { computed, ref } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { useToolConnectionsStore } from "../../../stores/toolConnections";
import { attachmentsClient, type ReadPath } from "../../../api/files/AttachmentsClient";
import { splitAttachments, DOCUMENT_FILE, fileText, markScan, withReadText } from "../../../utils/content/attachments";
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
    kind?: string;
    /** Armory kept the original, so its pages can be shown to the model. */
    stored?: boolean;
    /** The original file, kept only while Reader can still be asked to read it. */
    source?: File;
    ocr?: "reading" | "error";
    /** How the file was read beyond its text preview. */
    read?: ReadPath;
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
      // Every file goes up the same way. Each on its own: one slow or broken file doesn't hold up the rest.
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
          kind: result.kind,
          stored: result.file_id !== null,
          read: result.read ?? undefined,
          // Kept for "Read with OCR". A scan was already handled at upload.
          source: DOCUMENT_FILE.test(file.name) && !result.read ? file : undefined,
        });
      }).catch((err: unknown) => Object.assign(live, { state: "error", error: errorMessage(err) }));
    }
  }

  const canShowPages = (a: PendingAttachment): boolean => a.kind === "pdf" && a.stored === true;

  /** Whether the button shows. Without Reader, only attaching a stored PDF's pages is left. */
  function canRead(a: PendingAttachment): boolean {
    return a.state === "ready" && !!a.source && !a.read && (!connections.reason("reader") || canShowPages(a));
  }

  function showPages(a: PendingAttachment): void {
    Object.assign(a, { text: markScan(a.text), read: "pages", ocr: undefined });
  }

  /** Only on the user's request: Reader's text replaces the preview, else the model is shown the pages. */
  async function readWithOcr(id: number): Promise<void> {
    const live = attachments.value.find((a) => a.id === id);
    if (!live || !canRead(live) || live.ocr === "reading") return;
    if (connections.reason("reader")) return showPages(live);
    live.ocr = "reading";
    try {
      const result = await attachmentsClient.document(live.source!);
      if (result.read === "reader") {
        Object.assign(live, {
          text: withReadText(live.text, result.text), chars: result.char_count, truncated: result.truncated,
          read: "reader", ocr: undefined,
        });
      } else if (canShowPages(live)) {
        showPages(live);
      } else {
        throw new Error(live.kind === "image" ? "Reader could not read it. The model still sees the image." : "Reader could not read it.");
      }
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
    removeAttachment, canRead, readWithOcr, restoreAttachments, onPick, onDragOver, onDragLeave, onDrop, onPaste,
  };
}
