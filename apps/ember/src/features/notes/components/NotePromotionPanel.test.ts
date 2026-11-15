import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NotePromotionPanel from "./NotePromotionPanel.vue";
import { brainsClient, promotionsClient } from "../../brains/api/BrainsClient";
vi.mock("../../brains/api/BrainsClient", () => ({ brainsClient: { destinations: vi.fn() },
  promotionsClient: { list: vi.fn(), suggestions: vi.fn(), review: vi.fn(), suggest: vi.fn(), publish: vi.fn(), dismiss: vi.fn() } }));
const hash = "a".repeat(64);
const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
afterEach(() => { HTMLDialogElement.prototype.showModal = realShow; HTMLDialogElement.prototype.close = realClose; });
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  vi.resetAllMocks();
  vi.mocked(brainsClient.destinations).mockResolvedValue(["personal", "instance"].map(scope => ({
    id: scope, scope: scope as "personal" | "instance", label: scope, enabled: true, writable: true,
    folder: "Inbox", revision: 1, generation: "gen", status: "configured" })));
  vi.mocked(promotionsClient.list).mockResolvedValue([]); vi.mocked(promotionsClient.suggestions).mockResolvedValue([]);
  vi.mocked(promotionsClient.review).mockResolvedValue({ note_id: "note", title: "Procedure", body: "Durable instructions",
    source_hash: hash, source_revision: "now", agent_readable: false });
});
it("requires explicit shared audience review and retains a refused publication draft", async () => {
  const w = mount(NotePromotionPanel, { props: { noteId: "note", dirty: false } }); await flushPromises();
  await w.findAll("button").find(b => b.text() === "Promote to Obsidian")!.trigger("click"); await flushPromises();
  expect(w.get("select").element.value).toBe("personal");
  await w.get("select").setValue("instance");
  const publish = w.findAll("button").find(b => b.text() === "Publish document")!;
  expect(publish.attributes("disabled")).toBeDefined();
  await w.get('[role="switch"]').setValue(true);
  await w.get("textarea").setValue("Reviewed shared draft");
  vi.mocked(promotionsClient.publish).mockRejectedValue(new Error("Destination changed"));
  await publish.trigger("click"); await flushPromises();
  expect((w.get("textarea").element as HTMLTextAreaElement).value).toBe("Reviewed shared draft");
  expect(w.get('[role="alert"]').text()).toBe("Destination changed");
  expect(promotionsClient.publish).toHaveBeenCalledWith("note", expect.objectContaining({ scope: "instance", shared_audience_reviewed: true, source_hash: hash }));
});
it("default AI review sends no private IDs and never publishes", async () => {
  vi.mocked(promotionsClient.suggest).mockResolvedValue([]);
  const w = mount(NotePromotionPanel, { props: { noteId: "note", dirty: false } }); await flushPromises();
  await w.findAll("button").find(b => b.text() === "Suggest promotions")!.trigger("click"); await flushPromises();
  expect(promotionsClient.suggest).toHaveBeenCalledWith([], []);
  expect(promotionsClient.publish).not.toHaveBeenCalled();
});

it("ignores a review resolving after the selected note changes", async () => {
  let finish!: (value: Awaited<ReturnType<typeof promotionsClient.review>>) => void;
  vi.mocked(promotionsClient.review).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const w = mount(NotePromotionPanel, { props: { noteId: "note", sourceVersion: "1", dirty: false } });
  await flushPromises();
  await w.findAll("button").find(b => b.text() === "Promote to Obsidian")!.trigger("click"); await flushPromises();
  await w.setProps({ noteId: "other", sourceVersion: "2" });
  finish({ note_id: "note", title: "Old", body: "Old content", source_hash: hash, source_revision: "1", agent_readable: false });
  await flushPromises();
  expect(w.find("textarea").exists()).toBe(false);
  expect(w.find("dialog[open]").exists()).toBe(false);
  w.unmount();
});
it("retains edited publication text and path after closing and switching notes", async () => {
  const w = mount(NotePromotionPanel, { props: { noteId: "note", dirty: false } }); await flushPromises();
  const open = () => w.findAll("button").find(b => b.text() === "Promote to Obsidian")!.trigger("click");
  await open(); await flushPromises();
  await w.get("textarea").setValue("My retained Markdown");
  await w.get('input[maxlength="500"]').setValue("Inbox/custom.md");
  await w.get("dialog").trigger("cancel");
  await open(); await flushPromises();
  expect(w.get<HTMLTextAreaElement>("textarea").element.value).toBe("My retained Markdown");
  await w.setProps({ noteId: "other" }); await flushPromises();
  await w.setProps({ noteId: "note", sourceVersion: "new" }); await flushPromises();
  await open(); await flushPromises();
  expect(w.get<HTMLTextAreaElement>("textarea").element.value).toBe("My retained Markdown");
  expect(w.get<HTMLInputElement>('input[maxlength="500"]').element.value).toBe("Inbox/custom.md");
  expect(promotionsClient.review).toHaveBeenCalledTimes(2);
  w.unmount();
});
it("ignores publication completion after selecting another note", async () => {
  let finish!: (value: Awaited<ReturnType<typeof promotionsClient.publish>>) => void;
  vi.mocked(promotionsClient.publish).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const w = mount(NotePromotionPanel, { props: { noteId: "note", dirty: false } }); await flushPromises();
  await w.findAll("button").find(b => b.text() === "Promote to Obsidian")!.trigger("click"); await flushPromises();
  await w.findAll("button").find(b => b.text() === "Publish document")!.trigger("click");
  await w.setProps({ noteId: "other" });
  finish({ path: "old.md" } as Awaited<ReturnType<typeof promotionsClient.publish>>); await flushPromises();
  expect(w.text()).not.toContain("Published old.md");
  expect(w.find("dialog[open]").exists()).toBe(false);
  w.unmount();
});

it("retains each suggestion draft when another suggestion opens without changing the selected Note", async () => {
  vi.mocked(promotionsClient.suggestions).mockResolvedValue(["a", "b"].map(id => ({
    id, note_id: id, title: id, source_hash: hash, source_revision: "now", scope: "personal",
    destination_revision: 1, generation: "gen", folder: "Inbox", tags: [], reason: "Useful", draft: `Draft ${id}`,
  })));
  vi.mocked(promotionsClient.review).mockImplementation(async id => ({ note_id: id, title: id, body: id,
    source_hash: hash, source_revision: "now", agent_readable: false }));
  const w = mount(NotePromotionPanel, { props: { noteId: "selected", dirty: false } }); await flushPromises();
  const review = (index: number) => w.findAll("article")[index]!.findAll("button").find(b => b.text() === "Review suggestion")!;
  await review(0).trigger("click"); await flushPromises();
  await w.get("textarea").setValue("Edited suggestion A");
  await w.get('input[maxlength="500"]').setValue("Inbox/a-custom.md");
  await w.get("dialog").trigger("cancel");
  await review(1).trigger("click"); await flushPromises();
  await w.get("textarea").setValue("Edited suggestion B");
  await w.get("dialog").trigger("cancel");
  await review(0).trigger("click"); await flushPromises();
  expect(w.get<HTMLTextAreaElement>("textarea").element.value).toBe("Edited suggestion A");
  expect(w.get<HTMLInputElement>('input[maxlength="500"]').element.value).toBe("Inbox/a-custom.md");
  await w.get("dialog").trigger("cancel");
  await review(1).trigger("click"); await flushPromises();
  expect(w.get<HTMLTextAreaElement>("textarea").element.value).toBe("Edited suggestion B");
  w.unmount();
});
