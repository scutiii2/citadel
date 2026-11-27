# Shared Files Store, Part 2 Implementation Plan

> **For agentic workers:** use superpowers:executing-plans. One agent runs every task in order and reports once at the
> end. No subagent review, no worktree, no branch, no baseline run, no full suite.

**Goal:** Ember sends every file except audio and OCR documents through one upload route, and gets back one reply shape
and one file reference line.

**Architecture:** Stronghold gets `POST /attachments/file`: it reads a text preview, hands the original to Armory's
`/upload/file` (built in Part 1) and, for CSV and Excel, also registers the table. Portcullis passes the route through.
Legion and Ember learn the new `[File file_id: …]` line and keep reading the old ones.

**Tech Stack:** Python 3.14, FastAPI, httpx, pytest through `uv`; Vue 3, TypeScript, Vitest through `pnpm`.

**Spec:** `docs/superpowers/specs/2026-11-26-shared-files-store-design.md` (Part 2). Needs Part 1 (commit `97492a9d`).

## Global Constraints

- All paths are relative to the Citadel folder. Run each test command from the folder it names.
- Reference line: `[File file_id: <id> | <kind> | <n> pages | expires_at: <t> | …]`; `pages` only for PDF and image.
- Old `[Image file_id: …]` and `[PDFMerger file_id: …]` lines keep working.
- Upload permission stays `files.upload`. Nothing visible changes in Ember.
- 15 MB per file, 20 MB for audio.
- The old Portcullis and Stronghold routes stay.
- If the store is unavailable and the text is readable, the text is attached without a file id. An image or audio file
  shows an error.
- Audio and "Read with OCR" keep their current routes until Part 3. The `table_id` line stays until Part 4.
- Keep each file's line endings. Never add a reduced-motion setting or query.

## Choices this plan makes

- The reply carries one field the spec does not list, `table`, so the `table_id` line still appears until Part 4.
- A refusal from Armory (not an outage) is shown for PDF, image and audio. A text, code, Word or spreadsheet file is
  still attached as text, as it is today.
- Armory needs no change.

## File Structure

| File | Change |
|---|---|
| `apps/stronghold/src/attachments/services.py` | `ArmoryUploads.file` |
| `apps/stronghold/src/attachments/routes.py` | `POST /attachments/file`, `FileOut` |
| `apps/portcullis/src/routes/attachments.py` | pass-through route |
| `apps/portcullis/src/services/stronghold_forwarder.py` | longer timeout and readable 502 for uploads |
| `apps/legion/src/runtime/images.py`, `agents/roles/orchestrator/delegation.py` | read the new line |
| `apps/ember/src/api/files/AttachmentsClient.ts` | `file()` replaces `pdf`, `table`, `text` |
| `apps/ember/src/utils/content/attachments.ts` | `fileHeader`, `fileText` |
| `apps/ember/src/features/chat/composables/useComposerAttachments.ts` | one upload path |
| `apps/ember/src/components/content/ChatAttachment.vue` | preview from the new line |

---

### Task 1: Stronghold's one upload route

**Files:**
- Modify: `apps/stronghold/src/attachments/services.py`, `apps/stronghold/src/attachments/routes.py`
- Test: `apps/stronghold/tests/test_attachments.py`

**Interfaces:**
- Consumes: Armory `POST /upload/file` answering `{file_id, name, kind, pages, size, expires_at}`.
- Produces: `POST /attachments/file` with body `{filename, data}` answering
  `{filename, text, char_count, truncated, file_id|null, kind, size, pages|null, expires_at|null, table|null}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_attachments.py` add `("file", "a.txt")` to the parametrize list of
`test_every_route_needs_the_requester`, and append:

```python
# --- file (every kind) ----------------------------------------------------------------------

_KINDS = {".png": ("image", 1), ".pdf": ("pdf", 2), ".csv": ("table", 0), ".mp3": ("audio", 0)}


def armory_files(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/upload/table":
        return httpx.Response(200, json=TABLE)
    name = request.content.split(b'filename="')[1].split(b'"')[0].decode()
    kind, pages = _KINDS.get(name[name.rfind("."):], ("text", 0))
    return httpx.Response(200, json={"file_id": "f_1", "name": name, "kind": kind, "pages": pages, "size": 3,
                                     "expires_at": 2000000000})


def test_a_text_file_is_stored_and_previewed(client: TestClient, armory, platform) -> None:
    armory.handler = armory_files

    response = post(client, "file", "C:\\Users\\me\\notes.md", b"# hi")

    assert response.status_code == 200, response.text
    assert response.json() == {"filename": "notes.md", "text": "# hi", "char_count": 4, "truncated": False,
                               "file_id": "f_1", "kind": "text", "size": 4, "pages": None,
                               "expires_at": 2000000000, "table": None}
    sent = armory.requests[-1]
    assert sent.url.path == "/upload/file" and requester(sent)["username"] == "ana"
    assert caller(sent, "armory") == "stronghold"
    assert "attachments.file" in logged(platform)


def test_an_image_has_pages_and_no_preview(client: TestClient, armory) -> None:
    armory.handler = armory_files

    result = post(client, "file", "photo.png", b"png").json()

    assert (result["kind"], result["pages"], result["text"], result["table"]) == ("image", 1, "", None)


def test_a_spreadsheet_is_also_registered_as_a_table(client: TestClient, armory) -> None:
    armory.handler = armory_files

    result = post(client, "file", "sales.csv", b"region,units\nEU,1\n").json()

    assert result["table"]["table_id"] == "tbl-1" and result["file_id"] == "f_1"
    assert sorted(r.url.path for r in armory.requests) == ["/upload/file", "/upload/table"]


def test_a_failed_table_leaves_the_file_attached(client: TestClient, armory) -> None:
    armory.handler = lambda r: (httpx.Response(400, json={"error": "no header"}) if r.url.path == "/upload/table"
                                else armory_files(r))

    result = post(client, "file", "sales.csv", b"x\n").json()

    assert result["file_id"] == "f_1" and result["table"] is None


def test_without_the_store_readable_text_is_still_attached(client: TestClient, armory, platform) -> None:
    armory.handler = down

    result = post(client, "file", "notes.md", b"# hi").json()

    assert (result["file_id"], result["text"], result["expires_at"]) == (None, "# hi", None)
    assert "attachments.file" not in logged(platform)
    for name in ("photo.png", "voice.mp3", "scan.pdf"):  # nothing readable: the failure shows
        refused = post(client, "file", name, b"%PDF-scan")
        assert refused.status_code == 502 and refused.json()["detail"] == "File storage is unavailable", name


def test_a_refusal_shows_for_a_picture_but_text_is_still_attached(client: TestClient, armory) -> None:
    armory.handler = lambda r: httpx.Response(400, json={"error": "Your files would use more than 500 MB."})

    refused = post(client, "file", "photo.png", b"png")

    assert refused.status_code == 400 and "500 MB" in refused.json()["detail"]
    assert post(client, "file", "notes.md", b"# hi").json()["file_id"] is None


def test_files_that_cannot_be_used_never_reach_armory(client: TestClient, armory) -> None:
    unknown = post(client, "file", "movie.mp4", b"\x00\x01")
    binary = post(client, "file", "binary.txt", bytes(range(128, 256)) * 10)

    assert unknown.status_code == 400 and "Can't read '.mp4' files" in unknown.json()["detail"]
    assert binary.status_code == 400
    assert armory.requests == []
```

- [ ] **Step 2: See them fail**

Run in `apps/stronghold`: `uv run pytest tests/test_attachments.py -q`
Expected: the new tests fail with 404.

- [ ] **Step 3: The Armory call**

In `attachments/services.py` add under `_LONG = 120.0`:

```python
_STORE_DOWN = "File storage is unavailable"
```

and to `ArmoryUploads`:

```python
    async def file(self, who: Requester, filename: str, content: bytes) -> dict:
        """Armory's /upload/file: it keeps any accepted file and answers with its id and kind."""
        body = await self._upload("/upload/file", who, filename, content, _STORE_DOWN)
        if (not isinstance(body.get("file_id"), str) or not isinstance(body.get("kind"), str)
                or not isinstance(body.get("pages"), int) or not isinstance(body.get("expires_at"), (int, float))):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, _STORE_DOWN)
        return body
```

Change the class docstring to
`"""Armory's upload routes: it keeps the file for the file, data and PDF tools and answers with an id."""`.

- [ ] **Step 4: The route**

In `attachments/routes.py`:

Add imports `import asyncio` and `from pathlib import PurePosixPath`, and extend the extraction import to
`MAX_FILE_BYTES, PLAIN_TEXT_SUFFIXES, ExtractionError, extract_text_async`.

After `_MAX_DOCUMENT_BYTES`:

```python
# Files whose text Stronghold can read as a preview.
_PREVIEW_SUFFIXES = PLAIN_TEXT_SUFFIXES | {".pdf", ".docx", ".xlsx", ".xlsm"}
```

After `class DocumentIn`:

```python
class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_base64(_MAX_AUDIO_BYTES))
```

After `class DocumentOut`:

```python
class FileOut(TextOut):
    """One uploaded file. `file_id` is None when Armory could not keep it and only its text is attached."""

    file_id: str | None = None
    kind: str = "text"
    size: int
    pages: int | None = None
    expires_at: float | None = None
    table: TableOut | None = None
```

Add this helper beside `_audio`, and use it in `attachment_table` in place of its inline `TableOut(...)`:

```python
def _table_out(table: dict, filename: str) -> TableOut:
    return TableOut(table_id=table["table_id"], filename=str(table.get("filename", filename)),
                    rows=int(table.get("rows", 0)), columns=[str(name) for name in table.get("columns", [])],
                    sheet=table.get("sheet"), notes=[str(note) for note in table.get("notes", [])])
```

Add the route before `@router.post("/table")`:

```python
@router.post("/file")
async def attachment_file(body: UploadIn, who: Requester = Depends(current_requester),
                          uploads: ArmoryUploads = Depends(get_uploads),
                          platform: PortcullisClient = Depends(get_platform)) -> FileOut:
    """One route for every file: Armory keeps the original, and its text is read here as a preview."""
    filename = _name(body.filename)
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in _PREVIEW_SUFFIXES and suffix not in _PDF_SUFFIXES and suffix not in _AUDIO_SUFFIXES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Can't read '{suffix or 'extensionless'}' files - try a text, code, image, audio, .pdf, .docx or .xlsx file.")
    content = _decode(body.data, _MAX_AUDIO_BYTES, "The file is larger than 20 MB")
    preview = None
    if suffix in _PREVIEW_SUFFIXES:
        try:
            preview = await extract_text_async(filename, content)
        except ExtractionError as error:
            if suffix != ".pdf":  # a scan has no text and is still worth keeping
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    async def table() -> dict | None:
        """The data tools' copy of a spreadsheet; the file stays attached without it."""
        if suffix not in _TABLE_SUFFIXES:
            return None
        try:
            return await uploads.table(who, filename, content)
        except HTTPException:
            return None

    stored, registered = await asyncio.gather(uploads.file(who, filename, content), table(), return_exceptions=True)
    if isinstance(registered, BaseException):
        raise registered
    if isinstance(stored, BaseException):
        # With readable text the question can still go out: always during an outage, and for text-like files, which
        # never needed the store, after a refusal too.
        outage = isinstance(stored, HTTPException) and stored.status_code == status.HTTP_502_BAD_GATEWAY
        if not isinstance(stored, HTTPException) or preview is None or not (outage or suffix not in _PDF_SUFFIXES):
            raise stored
        stored = None
    else:
        await platform.log_action(who.uid, "attachments.file", f"Attached '{filename}' ({len(content):,} bytes)")
    kept = {} if stored is None else {"file_id": stored["file_id"], "kind": stored["kind"],
                                      "pages": stored["pages"] or None, "expires_at": stored["expires_at"]}
    return FileOut(filename=filename, size=len(content), text=preview.text if preview else "",
                   char_count=preview.char_count if preview else 0,
                   truncated=preview.truncated if preview else False,
                   table=_table_out(registered, filename) if registered else None, **kept)
```

Change the module docstring's second sentence to "Text is read here and sent back; the files themselves go to Armory."

- [ ] **Step 5: Run the tests**

Run in `apps/stronghold`: `uv run pytest tests/test_attachments.py -q`
Expected: all pass.

---

### Task 2: Portcullis passes it through

**Files:**
- Modify: `apps/portcullis/src/routes/attachments.py`, `apps/portcullis/src/services/stronghold_forwarder.py`
- Test: `apps/portcullis/tests/test_attachments.py`

**Interfaces:**
- Consumes: Stronghold `POST /attachments/file` (Task 1).
- Produces: `POST /api/attachments/file`, permission `files.upload`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_attachments.py` add `("file", "a.txt")` to `ROUTES`, and add after
`test_a_big_body_is_not_cut_off_on_the_way`:

```python
def test_a_20_mb_upload_is_passed_on_with_a_long_timeout(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"ok": True})

    response = client.post("/api/attachments/file", json=body("a.mp3", b"x" * (20 * 1024 * 1024)))

    assert response.status_code == 200
    assert upstream.requests[-1].extensions["timeout"]["read"] == 150.0


def test_an_upload_keeps_the_reason_storage_failed(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(502, json={"detail": "File storage is unavailable"})

    response = client.post("/api/attachments/file", json=body("a.png"))

    assert response.status_code == 502 and response.json() == {"detail": "File storage is unavailable"}
```

- [ ] **Step 2: See them fail**

Run in `apps/portcullis`: `uv run pytest tests/test_attachments.py -q`
Expected: the new cases fail with 404 or 405.

- [ ] **Step 3: Route and forwarder**

In `routes/attachments.py`, before `@router.post("/text")`:

```python
@router.post("/file")
async def attachment_file(request: Request, account: Account = Depends(require_chat),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    """One upload route for every kind of file."""
    return await pass_on(request, stronghold, account, "/attachments/file")
```

In `stronghold_forwarder.py` add after `_STREAM_TIMEOUT`:

```python
# One upload is read, stored and perhaps parsed as a table before Stronghold answers.
_UPLOAD_TIMEOUT = httpx.Timeout(150.0, connect=10.0)
_UPLOAD_PATH = "/attachments/file"
```

Replace the `timeout = ...` line in `forward` with:

```python
        if stack and path.endswith("/compact"):
            timeout = _STACK_COMPACTION_TIMEOUT
        elif path == _UPLOAD_PATH:
            timeout = _UPLOAD_TIMEOUT
        else:
            timeout = _TIMEOUT
```

and replace the `tool_service = ...` line with:

```python
        # Routes whose 502 carries a detail that is safe and useful to show.
        tool_service = path in _CONNECTION_FEATURES or path == _UPLOAD_PATH or path.startswith("/admin/tool-services/")
```

- [ ] **Step 4: Run the tests**

Run in `apps/portcullis`: `uv run pytest tests/test_attachments.py -q`
Expected: all pass.

---

### Task 3: Legion reads the new line

**Files:**
- Modify: `apps/legion/src/runtime/images.py`, `apps/legion/src/agents/roles/orchestrator/delegation.py`,
  `apps/legion/agents/ember.json`, `apps/legion/README.md`
- Test: `apps/legion/tests/test_images.py`, `apps/legion/tests/test_delegation.py`

**Interfaces:**
- Consumes: the reference line `[File file_id: <id> | image | …]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_images.py`:

```python
def test_the_file_line_names_images_only_when_its_kind_is_image():
    def line(file_id, kind):
        return f"[File file_id: {file_id} | {kind} | 1 pages | expires_at: 1.5 | preserve this file_id]"

    question = line("new", "image") + line("doc", "pdf") + ref("old")
    assert images.references(question, []) == ["new", "old"]
```

Append to `tests/test_delegation.py`:

```python
def test_file_references_survive_delegation():
    question = ('Look\n[[ATTACHMENT filename="notes.md" chars="4" truncated="false"]]\n'
                '[File file_id: f_notes | text | expires_at: 1]\nsecret text\n[[/ATTACHMENT]]')
    token = delegation.bind_attachments(question, [])
    try:
        assert delegation._attachments.get() == "notes.md: [File file_id: f_notes | text | expires_at: 1]"
        nested = delegation.bind_attachments("notes.md: [File file_id: f_notes | text | expires_at: 1]", [])
        try:
            assert "f_notes" in delegation._attachments.get()
        finally:
            delegation.reset_attachments(nested)
    finally:
        delegation.reset_attachments(token)
```

- [ ] **Step 2: See them fail**

Run in `apps/legion`: `uv run pytest tests/test_images.py tests/test_delegation.py -q`
Expected: the two new tests fail.

- [ ] **Step 3: The patterns**

In `images.py` replace `_REFERENCE` with:

```python
# `[File file_id: X | image | …]`, and the older `[Image|PDFMerger file_id: X | N pages | image …]`.
_REFERENCE = re.compile(
    r"\[(?:File file_id: (?=[A-Za-z0-9_-]{1,100} \| image(?: \||\]))"
    r"|(?:Image|PDFMerger) file_id: (?=[A-Za-z0-9_-]{1,100} \| \d+ pages \| image(?: \||\])))"
    r"([A-Za-z0-9_-]{1,100})")
```

and change the module docstring's example to `` `[File file_id: <id> | image | 1 pages ...]` ``.

In `delegation.py`, in `bind_attachments`, change `(?:PDFMerger|Image)` to `(?:File|PDFMerger|Image)` in both patterns.

- [ ] **Step 4: Agent text**

In `agents/ember.json` replace `copy its [Image file_id: ...] line verbatim` with
`copy its [File file_id: ...] line verbatim`.

In `README.md`, "Attached images", replace `` `[Image file_id: <id> | ...]` `` with
`` `[File file_id: <id> | image | ...]` (older chats say `[Image file_id: <id> | ...]`) ``.

- [ ] **Step 5: Run the tests**

Run in `apps/legion`: `uv run pytest tests/test_images.py tests/test_delegation.py tests/test_agent_spec.py -q`
Expected: all pass.

---

### Task 4: Ember uploads one way

**Files:**
- Modify: `apps/ember/src/api/files/AttachmentsClient.ts`, `apps/ember/src/utils/content/attachments.ts`,
  `apps/ember/src/features/chat/composables/useComposerAttachments.ts`,
  `apps/ember/src/components/content/ChatAttachment.vue`
- Test: `AttachmentsClient.test.ts`, `attachments.test.ts`, `features/chat/components/ChatInput.test.ts`,
  `features/chat/components/MessageList.test.ts`

**Interfaces:**
- Consumes: `POST /api/attachments/file` (Task 2).
- Produces: `attachmentsClient.file(file: File): Promise<AttachmentFile>`, `fileHeader(f)`, `fileText(file)`.

- [ ] **Step 1: Write the failing tests**

`AttachmentsClient.test.ts`: replace the `attachmentsClient.table` and `attachmentsClient.pdf` blocks with:

```ts
describe("attachmentsClient.file", () => {
  it("posts any file as base64 to the one upload endpoint", async () => {
    await attachmentsClient.file(new File(["a,b\n1,2\n"], "sales.csv"));

    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/attachments/file", {
      filename: "sales.csv", data: btoa("a,b\n1,2\n"),
    });
  });

  it("refuses a file over the limit before uploading it", async () => {
    const big = new File(["x"], "big.pdf");
    Object.defineProperty(big, "size", { value: 16 * 1024 * 1024 });

    await expect(attachmentsClient.file(big)).rejects.toThrow("Too large");
    expect(request).not.toHaveBeenCalled();
  });
});
```

`attachments.test.ts`: add `fileHeader, fileText` to the import, and append:

```ts
describe("stored files", () => {
  const stored = {
    filename: "photo.png", file_id: "f_1", kind: "image", size: 3, pages: 1, expires_at: 99,
    text: "", char_count: 0, truncated: false, table: null,
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
```

`ChatInput.test.ts`:

1. Mock: `({ attachmentsClient: { file: vi.fn(), dictate: vi.fn() } })`.
2. Replace the `text`, `pdf`, `table` constants with:

```ts
const upload = vi.mocked(attachmentsClient.file);

const uploaded = (over: Partial<AttachmentFile> = {}): AttachmentFile => ({
  filename: "scan.pdf", file_id: "file-1", kind: "pdf", size: 1, pages: 2, expires_at: 2000000000,
  text: "", char_count: 0, truncated: false, table: null, ...over,
});
const SHEET = { table_id: "tbl-1", filename: "sales.csv", rows: 1200, columns: ["region", "units"], sheet: null, notes: [] };
```

and import `type AttachmentFile` from the client module.

3. In `beforeEach` replace the three mock lines with
   `upload.mockReset(); upload.mockImplementation(async (f: File) => uploaded({ filename: f.name }));`
4. In "turns a pasted file into an attachment" expect `upload` where it expected `pdf`.
5. Every `expect(text).not.toHaveBeenCalled()` (the two paste tests and "leaves dragged text alone") asserts `upload`,
   and "attaches files dropped on the form" expects `upload` to have been called exactly once with the dropped file.
6. In "shows a file ember_api could not read" use `upload.mockRejectedValue(...)`.
7. Replace the `attaching a table` and `original PDF attachments` blocks with:

```ts
describe("attaching a table", () => {
  it("uploads a .csv once and puts the file and table ids in the sent question", async () => {
    upload.mockResolvedValue(uploaded({ filename: "sales.csv", kind: "table", pages: null, text: "extracted", char_count: 9, table: SHEET }));
    const wrapper = mountInput();
    const sheet = file("sales.csv");

    await wrapper.find("form").trigger("drop", { dataTransfer: drag(["Files"], [sheet]) });
    await flushPromises();

    expect(upload).toHaveBeenCalledExactlyOnceWith(sheet);
    expect(wrapper.find(".attachments li").text()).toContain("1,200 rows, 2 columns");
    await wrapper.find("textarea").setValue("total units per region?");
    await wrapper.find("form").trigger("submit");
    const sent = wrapper.emitted("send")![0]![0] as string;
    expect(sent).toContain("[File file_id: file-1 | table |");
    expect(sent).toContain("table_id: tbl-1");
    expect(sent).toContain("extracted");
  });

  it("still attaches the preview, and says so, when the table could not be made", async () => {
    upload.mockResolvedValue(uploaded({ filename: "sales.xlsx", kind: "table", pages: null, text: "extracted", char_count: 9 }));
    const wrapper = mountInput();

    await wrapper.find("form").trigger("drop", { dataTransfer: drag(["Files"], [file("sales.xlsx")]) });
    await flushPromises();

    expect(wrapper.find(".attachments li").classes()).not.toContain("error");
    await wrapper.find("textarea").setValue("summarise");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")![0]![0] as string).toContain("could not be loaded");
  });
});
```

```ts
describe("stored attachments", () => {
  it("sends file ids in attachment order even without a text preview", async () => {
    const wrapper = mountInput();
    upload.mockResolvedValueOnce(uploaded({ file_id: "first" }));
    upload.mockResolvedValueOnce(uploaded({ filename: "photo.png", file_id: "second", kind: "image", pages: 1 }));
    await wrapper.find("textarea").trigger("paste", { clipboardData: clipboard([file("scan.pdf"), file("photo.png")]) });
    await flushPromises();
    await wrapper.find("form").trigger("submit");
    const sent = wrapper.emitted("send")![0]![0] as string;
    expect(sent.indexOf("file_id: first")).toBeLessThan(sent.indexOf("file_id: second"));
    expect(sent).toContain("No text preview available");
    expect(sent.slice(sent.indexOf('[[ATTACHMENT filename="photo.png"'))).toContain("[File file_id: second | image | 1 pages");
  });
  it("shows storage errors instead of sending a misleading text-only file", async () => {
    upload.mockRejectedValue(new Error("File storage is unavailable"));
    const wrapper = mountInput();
    await wrapper.find("textarea").trigger("paste", { clipboardData: clipboard([file("scan.pdf")]) });
    await flushPromises();
    expect(wrapper.find(".attachments li").classes()).toContain("error");
    expect(wrapper.find(".attachments li").text()).toContain("File storage is unavailable");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
  });
});
```

Delete the old "does not upload other files as tables" test: the server now decides. Any other use of `text`, `pdf` or
`table` mocks in the file moves to `upload` with `uploaded(...)`.

`MessageList.test.ts`: in "image attachments", replace the loop header and the attachment text with:

```ts
  for (const [label, text] of [
    ["PDFMerger", "[PDFMerger file_id: f_photo | 1 pages | image | expires_at: 2000000000]"],
    ["Image", "[Image file_id: f_photo | 1 pages | image | expires_at: 2000000000]"],
    ["File", "[File file_id: f_photo | image | 1 pages | expires_at: 2000000000 | preserve this file_id when delegating]"],
  ]) {
    it(`previews saved ${label} image references and opens the viewer`, async () => {
      const attachment = { filename: "image.png", chars: 0, truncated: false, text: text! };
```

- [ ] **Step 2: See them fail**

Run in `apps/ember`:
`pnpm vitest run src/api/files/AttachmentsClient.test.ts src/utils/content/attachments.test.ts src/features/chat/components/ChatInput.test.ts src/features/chat/components/MessageList.test.ts`
Expected: failures naming `file`, `fileHeader` and `fileText`.

- [ ] **Step 3: The client**

In `AttachmentsClient.ts` delete the `AttachmentPdf` interface and the `pdf`, `text` and `table` methods. Keep
`AttachmentText` only if something still uses it (nothing does after this change, so delete it). Add:

```ts
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
```

and as a method of `attachmentsClient`:

```ts
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
```

- [ ] **Step 4: The lines**

In `attachments.ts` change the type import to
`import type { AttachmentFile, AttachmentTable } from "../../api/files/AttachmentsClient";`, delete `PDF_FILE`, and add
after `tableHeader`:

```ts
/** The first line of a stored attachment: the id the file tools need and what the file is. */
export function fileHeader(f: { file_id: string | null; kind: string; pages: number | null; expires_at: number | null }): string {
  const pages = f.pages ? ` | ${f.pages} pages` : "";
  return `[File file_id: ${f.file_id} | ${f.kind}${pages} | expires_at: ${f.expires_at} | preserve this file_id when delegating]`;
}

/** What one uploaded file puts into the question: its id line, the table line, then the preview. */
export function fileText(file: AttachmentFile): string {
  const id = file.file_id ? `${fileHeader(file)}\n` : "";
  const table = TABLE_FILE.test(file.filename) ? tableHeader(file.table) : "";
  const preview = file.text || (file.kind === "image"
    ? "[No text preview available; inspect the original image when needed.]"
    : "[No text preview available; the original file is available for inspection.]");
  return id + table + preview;
}
```

- [ ] **Step 5: The composer and the preview**

In `useComposerAttachments.ts` change the import to
`import { splitAttachments, AUDIO_FILE, DOCUMENT_FILE, audioHeader, documentHeader, fileText } from "../../../utils/content/attachments";`
and replace everything in `addFiles` after the audio branch (from `if (PDF_FILE.test(file.name)) {` to the end of the
loop body) with:

```ts
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
```

In `ChatAttachment.vue` replace the `imageId` computed with:

```ts
const imageId = computed(() => {
  const found = props.attachment.text.match(
    /^\[(?:File file_id: ([A-Za-z0-9_-]{1,100}) \| image(?: \||\])|(?:Image|PDFMerger) file_id: ([A-Za-z0-9_-]{1,100}) \| \d+ pages \| image(?: \||\]))/,
  );
  return found?.[1] ?? found?.[2];
});
```

- [ ] **Step 6: Run the tests and the type check**

Run in `apps/ember`:
`pnpm vitest run src/api/files/AttachmentsClient.test.ts src/utils/content/attachments.test.ts src/features/chat/components/ChatInput.test.ts src/features/chat/components/MessageList.test.ts`

Run in `apps/ember`: `pnpm exec vue-tsc -b`

Expected: all pass, no type errors.

---

## Finish

- [ ] Commit once, staging only files this plan changed:

```bash
git add apps/stronghold apps/portcullis apps/legion apps/ember
git status --short
git commit -m "feat: one upload route for chat files, with one file reference line"
```

- [ ] Report once: what changed, which test files ran, what did not run. Say that Stronghold, Portcullis, Legion and
  Ember need a redeploy, after Part 1 is deployed.
- [ ] Ember reaches both the Windows app and the web build. Ask before pushing; then `pnpm run release` in
  `apps/ember`, copy `src-tauri/target/release/ember.exe` to `releases/Ember.exe`, push, and
  `python tools/publish_live.py` so the user can pull `live` and rebuild `ember` on Zima.
