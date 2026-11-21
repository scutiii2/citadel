import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import type { BrainFile } from "../../notes/api/BrainClient";
import { globalClient } from "../api/GlobalClient";
import GlobalFileDialog from "./GlobalFileDialog.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));
const client = vi.mocked(globalClient);

const ID = "a".repeat(32);
const file = (extra: Partial<BrainFile> = {}): BrainFile => ({
  id: ID, title: "Style guide", folder: "team", tags: [], source: "manual", last_editor: "user", agent_editable: false,
  edited: false, revision: 3, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-02T00:00:00", warning: null,
  shared_from: "", body: "Use <b>metric</b> units.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.get.mockResolvedValue(file());
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

async function open(props: { fileId: string | null; canWrite: boolean; maxChars?: number }) {
  wrapper = mount(GlobalFileDialog, { attachTo: document.body, props: { open: true, maxChars: 20_000, ...props }, global: { plugins: [createPinia()] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("GlobalFileDialog", () => {
  it("shows a file to a reader as plain text with no form", async () => {
    const w = await open({ fileId: ID, canWrite: false });
    expect(w.find("pre.text").text()).toBe("Use <b>metric</b> units.");
    expect(w.find("pre.text b").exists()).toBe(false);
    expect(w.find("input[aria-label='Title']").exists()).toBe(false);
    for (const name of ["Save", "Delete", "Create"]) expect(w.findAll("button").some((b) => b.text() === name)).toBe(false);
  });

  it("lets a writer change one field and sends only it with the opened revision", async () => {
    client.update.mockResolvedValue(file({ body: "new", revision: 4 }));
    const w = await open({ fileId: ID, canWrite: true });
    expect(button(w, "Save").attributes("disabled")).toBeDefined();
    await w.find("textarea[aria-label='Text']").setValue("new");
    await button(w, "Save").trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenCalledWith(ID, { body: "new" }, 3);
    expect(w.emitted("done")?.[0][0]).toContain("Saved");
  });

  it("says in words that the file changed when the server answers 412", async () => {
    client.update.mockRejectedValue(new ApiError(412, "This file changed since you opened it."));
    const w = await open({ fileId: ID, canWrite: true });
    await w.find("textarea[aria-label='Text']").setValue("new");
    await button(w, "Save").trigger("click");
    await flushPromises();
    expect(w.find("[role='alert']").text()).toContain("This file changed since someone opened it. Close it and open it again.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("creates a file when fileId is null and refuses a bad folder before sending", async () => {
    client.create.mockResolvedValue(file({ title: "Plan" }));
    const w = await open({ fileId: null, canWrite: true });
    await w.find("input[aria-label='Title']").setValue("Plan");
    await w.find("textarea[aria-label='Text']").setValue("Text");
    await w.find("input[aria-label='Folder']").setValue("a/b/c/d");
    expect(w.find("[role='alert']").text()).not.toBe("");
    expect(button(w, "Create").attributes("disabled")).toBeDefined();
    await w.find("input[aria-label='Folder']").setValue("team");
    await button(w, "Create").trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledWith({ title: "Plan", body: "Text", folder: "team" });
    expect(w.emitted("done")?.[0][0]).toContain("Created");
  });

  it("deletes only after confirmation", async () => {
    client.remove.mockResolvedValue(undefined);
    const w = await open({ fileId: ID, canWrite: true });
    await button(w, "Delete").trigger("click");
    expect(client.remove).not.toHaveBeenCalled();
    await w.findAll("button").filter((b) => b.text() === "Delete").at(-1)!.trigger("click");
    await flushPromises();
    expect(client.remove).toHaveBeenCalledWith(ID);
    expect(w.emitted("done")?.[0][0]).toContain("Deleted");
  });

  it("blocks Save above the text limit and says so in words", async () => {
    const w = await open({ fileId: ID, canWrite: true, maxChars: 10 });
    await w.find("textarea[aria-label='Text']").setValue("x".repeat(11));
    expect(button(w, "Save").attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("10");
  });
});
