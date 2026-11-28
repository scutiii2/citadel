import { computed, ref } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { useToolConnectionsStore } from "../../../stores/toolConnections";
import { attachmentsClient, type ReadPath } from "../../../api/files/AttachmentsClient";
import {
  splitAttachments, DOCUMENT_FILE, FILE_ONLY_QUESTION, fileText, imageFileId, isExpired, markScan, withReadText,
} from "../../../utils/content/attachments";
import { errorMessage } from "../../../utils/errors";

const PICTURE_FILE = /\.(png|jpe?g|webp|gif)$/i;

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
    /** The original file, kept only while Reader can still be asked to read it. */
    source?: File;
    ocr?: "reading" | "error";
    /** How the file was read beyond its text preview. */
    read?: ReadPath;
    /** A picture to preview: the file just added, or the stored one of a restored question. */
    picture?: File;
    imageId?: string;
    /** The server no longer has a restored question's file. */
    expired?: boolean;
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
        picture: PICTURE_FILE.test(file.name) ? file : undefined,
      };
      attachments.value.push(entry);
      const live = attachments.value[attachments.value.length - 1]!; // the reactive copy
      // Every file goes up the same way. Each on its own: one slow or broken file doesn't hold up the rest.
      void attachmentsClient.file(file).then((result) => {
        // Every stored PDF shows the model its pages, not only a scan.
        const shown = result.kind === "pdf" && result.file_id !== null && !!result.pages;
        const read = shown ? "pages" : (result.read ?? undefined);
        Object.assign(live, {
          state: "ready",
          text: shown ? markScan(fileText(result)) : fileText(result),
          chars: result.char_count,
          truncated: result.truncated,
          rows: result.table?.rows ?? 0,
          columns: result.table?.columns.length ?? 0,
          pages: result.pages ?? undefined,
          kind: result.kind,
          read,
          // Kept for "Read with OCR": only a file nothing has read yet.
          source: DOCUMENT_FILE.test(file.name) && !read ? file : undefined,
        });
      }).catch((err: unknown) => Object.assign(live, { state: "error", error: errorMessage(err) }));
    }
  }

  /** Whether "Read with OCR" shows. */
  function canRead(a: PendingAttachment): boolean {
    return a.state === "ready" && !!a.source && !a.read && !connections.reason("reader");
  }

  /** Only on the user's request: Reader's text replaces the preview. */
  async function readWithOcr(id: number): Promise<void> {
    const live = attachments.value.find((a) => a.id === id);
    if (!live || !canRead(live) || live.ocr === "reading") return;
    live.ocr = "reading";
    try {
      const result = await attachmentsClient.document(live.source!);
      if (result.read !== "reader") {
        throw new Error(live.kind === "image" ? "Reader could not read it. The model still sees the image." : "Reader could not read it.");
      }
      Object.assign(live, {
        text: withReadText(live.text, result.text), chars: result.char_count, truncated: result.truncated,
        read: "reader", ocr: undefined,
      });
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

  // The composer and the chat around it take file drops; dragged text or links
  // are left to the browser.
  function onDragOver(event: DragEvent): void {
    if (!hasFiles(event)) return;
    event.preventDefault(); // even without the permission: the browser must not open the file
    dragging.value = auth.hasPermission("files.upload");
  }

  function onDragLeave(event: DragEvent): void {
    // Moving over a child element also fires dragleave on the drop zone.
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
      attachments.value.push({
        id: nextAttachmentId++, filename: file.filename, state: "ready", text: file.text, chars: file.chars,
        truncated: file.truncated, rows: 0, columns: 0, error: "", imageId: imageFileId(file.text), expired: isExpired(file.text),
      });
    }
    // The stand-in text of a files-only question is added again on send.
    return files.length > 0 && text === FILE_ONLY_QUESTION ? "" : text;
  }

  /** The picture tile replaces the file's chip; a stored one needs the permission to load it. */
  function showsPicture(a: PendingAttachment): boolean {
    return a.state !== "error" && (!!a.picture || (!!a.imageId && auth.hasPermission("files.download")));
  }

  return {
    attachments, reading, ready, dragging,
    removeAttachment, canRead, readWithOcr, restoreAttachments, showsPicture, onPick, onDragOver, onDragLeave, onDrop, onPaste,
  };
}
