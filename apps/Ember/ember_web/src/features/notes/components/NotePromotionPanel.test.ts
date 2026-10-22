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
