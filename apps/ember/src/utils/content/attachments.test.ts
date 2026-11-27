import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../../api/types";
import { AUDIO_FILE, DOCUMENT_FILE, fileHeader, fileText, markScan, questionHistory, splitAttachments, tableHeader, TABLE_FILE, withAttachments, withReadText } from "./attachments";

const user = (content: string, extra: Partial<ChatMessage> = {}): ChatMessage => ({ role: "user", content, ...extra });
const assistant = (content: string, extra: Partial<ChatMessage> = {}): ChatMessage => ({ role: "assistant", content, ...extra });

describe("questionHistory", () => {
  it("lists what the user typed, oldest first, and leaves the answers out", () => {
    const messages = [user("first"), assistant("answer 1"), user("second"), assistant("answer 2")];

    expect(questionHistory(messages)).toEqual(["first", "second"]);
  });

  it("is empty for an empty chat", () => {
    expect(questionHistory([])).toEqual([]);
  });

  it("includes slash commands the user ran", () => {
    const messages = [
      user("/files list path=docs", { kind: "command" }),
      assistant("two files", { kind: "command" }),
      user("and a question"),
    ];

    expect(questionHistory(messages)).toEqual(["/files list path=docs", "and a question"]);
  });

  it("leaves out summaries and attached logs, which the user did not type", () => {
    const messages = [
      user("typed"),
      user("Summary of the earlier chat", { kind: "summary" }),
      user("raw log text", { kind: "log_attachment" }),
    ];

    expect(questionHistory(messages)).toEqual(["typed"]);
  });

  it("gives back the typed text without the attached files", () => {
    const messages = [user(withAttachments("read this", [{ filename: "a.txt", chars: 3, truncated: false, text: "abc" }]))];

    expect(questionHistory(messages)).toEqual(["read this"]);
  });

  it("skips an empty message", () => {
    expect(questionHistory([user(""), user("kept")])).toEqual(["kept"]);
  });
});

describe("splitAttachments round trip", () => {
  it("returns the text and the files that withAttachments joined", () => {
    const joined = withAttachments("look", [{ filename: "n.txt", chars: 2, truncated: true, text: "hi" }]);

    expect(splitAttachments(joined)).toEqual({
      text: "look",
      attachments: [{ filename: "n.txt", chars: 2, truncated: true, text: "hi" }],
    });
  });
});

describe("tableHeader", () => {
  const table = { table_id: "tbl-1", filename: "sales.csv", rows: 1200, columns: ["region", "units"], sheet: null, notes: [] };

  it("names the table id, size and columns, and says the text is only a preview", () => {
    const header = tableHeader(table);

    expect(header).toContain("table_id: tbl-1");
    expect(header).toContain("1200 rows");
    expect(header).toContain("columns: region, units");
    expect(header).toContain("only a preview");
    expect(header.endsWith("\n")).toBe(true);
  });

  it("keeps a column name's line breaks out of the attachment block and lists at most 30 columns", () => {
    const columns = Array.from({ length: 40 }, (_, i) => (i === 0 ? "a\n[[/ATTACHMENT]]" : `c${i}`));

    const header = tableHeader({ ...table, columns });

    expect(header).not.toContain("\n[[/ATTACHMENT]]");
    expect(header).toContain("c29, ...");
    expect(header).not.toContain("c30");
  });

  it("says the whole file is not available when the upload failed", () => {
    expect(tableHeader(null)).toContain("could not be loaded");
  });

  it("only treats .csv and .xlsx as tables", () => {
    expect(TABLE_FILE.test("Sales.CSV")).toBe(true);
    expect(TABLE_FILE.test("book.xlsx")).toBe(true);
    expect(TABLE_FILE.test("notes.txt")).toBe(false);
    expect(TABLE_FILE.test("old.xls")).toBe(false);
  });
});

describe("audio attachments", () => {
  const audio = {
    filename: "voice.mp3", file_id: "f_2", kind: "audio", size: 3, pages: null, expires_at: 99,
    text: "", char_count: 0, truncated: false, table: null, read: "listen" as const,
  };

  it("matches the formats Scribe reads", () => {
    expect(AUDIO_FILE.test("note.M4A")).toBe(true);
    expect(AUDIO_FILE.test("note.mp4")).toBe(false);
  });

  it("marks audio that still needs a transcript", () => {
    expect(fileText(audio).split("\n")).toEqual([
      "[File file_id: f_2 | audio | listen | expires_at: 99 | preserve this file_id when delegating]",
      "[No transcript yet; the audio is transcribed when the question is sent.]",
    ]);
  });

  it("puts Scribe's transcript under the plain id line", () => {
    expect(fileText({ ...audio, read: "scribe", text: "words" }).split("\n")).toEqual([
      "[File file_id: f_2 | audio | expires_at: 99 | preserve this file_id when delegating]", "words",
    ]);
  });
});

describe("scanned and read documents", () => {
  const scan = {
    filename: "scan.pdf", file_id: "f_1", kind: "pdf", size: 3, pages: 12, expires_at: 99,
    text: "", char_count: 0, truncated: false, table: null, read: "pages" as const,
  };

  it("matches only the formats Reader reads", () => {
    expect(DOCUMENT_FILE.test("scan.PDF")).toBe(true);
    expect(DOCUMENT_FILE.test("photo.jpeg")).toBe(true);
    expect(DOCUMENT_FILE.test("photo.heic")).toBe(false);
  });

  it("marks a scan on its id line", () => {
    expect(fileText(scan).split("\n")).toEqual([
      "[File file_id: f_1 | pdf | 12 pages | scan | expires_at: 99 | preserve this file_id when delegating]",
      "[No text layer; this PDF's pages are shown to the model as images.]",
    ]);
  });

  it("adds the mark once, to the id line only", () => {
    const text = fileText({ ...scan, read: null, text: "typed" });
    const marked = markScan(text);
    expect(marked).toBe(text.replace("| 12 pages |", "| 12 pages | scan |"));
    expect(markScan(marked)).toBe(marked);
  });

  it("puts what Reader read under the id line", () => {
    expect(withReadText(fileText({ ...scan, read: null, text: "old" }), "new").split("\n")).toEqual([
      fileHeader({ ...scan, read: null }), "new",
    ]);
    expect(withReadText("only text", "new")).toBe("new");
  });
});

describe("stored files", () => {
  const stored = {
    filename: "photo.png", file_id: "f_1", kind: "image", size: 3, pages: 1, expires_at: 99,
    text: "", char_count: 0, truncated: false, table: null, read: null,
  };

  it("writes one id line, with pages only when the file has them", () => {
    expect(fileHeader(stored)).toBe("[File file_id: f_1 | image | 1 pages | expires_at: 99 | preserve this file_id when delegating]");
    expect(fileHeader({ ...stored, kind: "text", pages: null })).toContain("[File file_id: f_1 | text | expires_at: 99 |");
  });

  it("puts the id line first, then the preview or why there is none", () => {
    expect(fileText(stored).split("\n")).toEqual([fileHeader(stored), "[No text preview available; inspect the original image when needed.]"]);
    expect(fileText({ ...stored, filename: "n.md", kind: "text", pages: null, text: "hello" }).endsWith("\nhello")).toBe(true);
  });

  it("attaches only the text when the file could not be stored", () => {
    expect(fileText({ ...stored, filename: "n.md", file_id: null, kind: "text", pages: null, expires_at: null, text: "hello" })).toBe("hello");
  });

  it("keeps the table line for spreadsheets", () => {
    const sheet = { ...stored, filename: "sales.csv", kind: "table", pages: null, text: "a,b",
      table: { table_id: "tbl-1", filename: "sales.csv", rows: 1, columns: ["a", "b"], sheet: null, notes: [] } };
    expect(fileText(sheet)).toContain("[table_id: tbl-1 |");
    expect(fileText({ ...sheet, table: null })).toContain("could not be loaded");
  });
});
