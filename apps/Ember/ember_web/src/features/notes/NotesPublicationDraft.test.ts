import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import NotesView from "./NotesView.vue";
import { notesClient } from "./api/NotesClient";
import { brainsClient, promotionsClient } from "../brains/api/BrainsClient";

vi.mock("./api/NotesClient", async original => ({
  ...(await original<typeof import("./api/NotesClient")>()),
  notesClient: { list: vi.fn() },
}));
vi.mock("../brains/api/BrainsClient", () => ({
  brainsClient: { destinations: vi.fn() },
  promotionsClient: { list: vi.fn(), suggestions: vi.fn(), review: vi.fn() },
}));
const show = HTMLDialogElement.prototype.showModal;
const close = HTMLDialogElement.prototype.close;
beforeEach(() => {
  vi.resetAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  vi.mocked(notesClient.list).mockResolvedValue([{ id: "a", title: "Saved Note", body: "Body", tags: [], agent_readable: false,
    last_editor: "user", created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00" }]);
  vi.mocked(brainsClient.destinations).mockResolvedValue([{ id: "personal", scope: "personal", label: "Personal", enabled: true,
    writable: true, folder: "Inbox", revision: 1, generation: "gen", status: "configured" }]);
  vi.mocked(promotionsClient.list).mockResolvedValue([]);
  vi.mocked(promotionsClient.suggestions).mockResolvedValue([]);
  vi.mocked(promotionsClient.review).mockResolvedValue({ note_id: "a", title: "Saved Note", body: "Body", source_hash: "a".repeat(64),
    source_revision: "2026-01-01T00:00:00", agent_readable: false });
});
afterEach(() => { HTMLDialogElement.prototype.showModal = show; HTMLDialogElement.prototype.close = close; });

it("retains publication drafts through All notes and reopening the editor", async () => {
  const w = mount(NotesView, { attachTo: document.body }); await flushPromises();
  const openNote = () => w.get('ul[aria-label="Notes"] button').trigger("click");
  const promote = () => w.findAll("button").find(b => b.text() === "Promote to Obsidian")!.trigger("click");
  await openNote(); await flushPromises();
  await promote(); await flushPromises();
  const panel = w.get(".note-promotions").element;
  await w.get('.note-promotions textarea').setValue("My publication draft");
  await w.get('.note-promotions input[maxlength="500"]').setValue("Inbox/retained.md");
  await w.get('dialog[aria-label="Review Obsidian publication"]').trigger("cancel");
  await w.get("button.back").trigger("click"); await flushPromises();
  expect(w.get(".library-publishing .note-promotions").element).toBe(panel);
  await openNote(); await flushPromises();
  expect(w.get(".publishing-tools .note-promotions").element).toBe(panel);
  await promote(); await flushPromises();
  expect(w.get<HTMLTextAreaElement>('.note-promotions textarea').element.value).toBe("My publication draft");
  expect(w.get<HTMLInputElement>('.note-promotions input[maxlength="500"]').element.value).toBe("Inbox/retained.md");
  w.unmount();
});
