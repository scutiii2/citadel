import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import { brainClient, type BrainFile, type BrainFileRow, type BrainSummary, type SearchHit } from "./api/BrainClient";
import NotesView from "./NotesView.vue";
import { useBrainStore } from "./stores/brain";

vi.mock("./api/BrainClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api/BrainClient")>()),
  brainClient: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), revert: vi.fn(), remove: vi.fn(), search: vi.fn(), summary: vi.fn() },
}));

vi.mock("../sharing/components/ShareDialog.vue", () => ({
  default: {
    props: ["open", "target"],
    template: '<div data-test="share-dialog">{{ target.kind }} {{ target.fileId }} {{ target.headings.join("|") }}</div>',
  },
}));

const client = vi.mocked(brainClient);

const row = (id: string, title: string, extra: Partial<BrainFileRow> = {}): BrainFileRow => ({
  id, title, folder: "", tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", chars: 5, warning: null, shared_from: "", ...extra,
});
const full = (id: string, title: string, body = "text", extra: Partial<BrainFileRow> = {}): BrainFile => {
  const { chars: _chars, ...rest } = row(id, title, extra);
  return { ...rest, body };
};
const SUMMARY: BrainSummary = { files: 2, bytes: 1200, skipped: 0, max_files: 500, max_total_bytes: 5_000_000, max_record_chars: 20_000 };

let wrapper: VueWrapper | null = null;

async function setup(files: BrainFileRow[] = [], options: { folders?: string[]; summary?: Partial<BrainSummary> } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  client.list.mockResolvedValue({ files, folders: options.folders ?? [] });
  client.summary.mockResolvedValue({ ...SUMMARY, ...options.summary });
  wrapper = mount(NotesView, { attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}

const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom does not implement <dialog>.showModal; give it the open flag the component reads.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  vi.useRealTimers();
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

const buttonByText = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text);
// The confirm button draws its label letter by letter, so it is found by class, not by text.
const confirm = () => document.body.querySelector<HTMLButtonElement>("dialog[open] .confirm");
const cancel = () => document.body.querySelector<HTMLButtonElement>("dialog[open] button.cancel");
const rows = (w: VueWrapper) => w.findAll("ul[aria-label='Files'] li");
const title = (w: VueWrapper) => w.get('input[aria-label="Title"]');
const text = (w: VueWrapper) => w.get('textarea[aria-label="File text"]');
async function open(w: VueWrapper, id: string) {
  await w.get(`[data-file-id="${id}"]`).trigger("click");
  await flushPromises();
}

describe("NotesView", () => {
  it("shares the saved file, listing its headings for a section", async () => {
    client.get.mockResolvedValue(full("a", "Tea", "# Brewing\nSteep.\n## Storage\nDry."));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await buttonByText(w, "Share a copy…")!.trigger("click");
    expect(w.get('[data-test="share-dialog"]').text()).toBe("file a Brewing|Storage");
  });

  it("does not offer to share while there are unsaved changes", async () => {
    client.get.mockResolvedValue(full("a", "Tea", "Body"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Edited");
    expect(buttonByText(w, "Share a copy…")!.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("Save your changes first.");
  });

  it("lists the server's files and shows the quota", async () => {
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    expect(rows(w).map((r) => r.text())[0]).toContain("Tea");
    expect(rows(w)).toHaveLength(2);
    expect(w.get('[data-test="quota"]').text()).toContain("2 of 500 files");
    expect(w.get('[data-test="quota"]').text()).not.toContain("full");
  });

  it("warns in words when the quota is nearly full, and refuses a new file when it is full", async () => {
    const near = await setup([row("a", "Tea")], { summary: { files: 410 } });
    expect(near.get('[data-test="quota"]').text()).toContain("nearly full");
    near.unmount();
    const w = await setup([row("a", "Tea")], { summary: { files: 500 } });
    expect(w.get('[data-test="quota"]').text()).toContain("full");
    await buttonByText(w, "New file")!.trigger("click");
    expect(w.find('input[aria-label="Title"]').exists()).toBe(false);
    expect(w.get('[role="status"]').text()).toContain("full");
  });

  it("names files that could not be read", async () => {
    const w = await setup([row("a", "Tea")], { summary: { skipped: 2 } });
    expect(w.text()).toContain("2 files in your brain folder could not be read");
  });

  it("a folder button shows that folder and its subfolders", async () => {
    const w = await setup(
      [row("a", "Top"), row("b", "Food", { folder: "food" }), row("c", "Tea", { folder: "food/tea" }), row("d", "Other", { folder: "foodie" })],
      { folders: ["food", "food/tea", "foodie"] },
    );
    await w.findAll('[aria-label="Folders"] button').find((b) => b.text() === "food")!.trigger("click");
    expect(rows(w).map((r) => r.find(".title").text())).toEqual(["Food", "Tea"]);
    await w.findAll('[aria-label="Folders"] button').find((b) => b.text() === "No folder")!.trigger("click");
    expect(rows(w).map((r) => r.find(".title").text())).toEqual(["Top"]);
  });

  it("searches the server after a pause, shows the snippet, and clearing restores the list", async () => {
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    // Fake only the timers the page's pause uses, after setup: flushPromises needs the real setImmediate.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const hit: SearchHit = { ...row("b", "Plan"), score: 2, snippet: "the plan for tea" };
    client.search.mockResolvedValue({ results: [hit] });
    await w.get('input[aria-label="Search files"]').setValue("plan");
    expect(client.search).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();
    expect(client.search).toHaveBeenCalledExactlyOnceWith("plan");
    expect(rows(w)).toHaveLength(1);
    expect(rows(w)[0]!.text()).toContain("the plan for tea");
    await w.get('input[aria-label="Search files"]').setValue("");
    await flushPromises();
    expect(rows(w)).toHaveLength(2);
  });

  it("opens a file by fetching its text", async () => {
    client.get.mockResolvedValue(full("a", "Tea", "Green tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    expect(client.get).toHaveBeenCalledExactlyOnceWith("a");
    expect((title(w).element as HTMLInputElement).value).toBe("Tea");
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Green tea");
  });

  it("shows why a file could not be opened and can try again", async () => {
    client.get.mockRejectedValueOnce(new ApiError(404, "No such file."));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    expect(w.get('[role="alert"]').text()).toContain("No such file.");
    client.get.mockResolvedValueOnce(full("a", "Tea", "Back"));
    await w.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Back");
  });

  it("creates a file in the folder that is showing, with a cleaned folder name", async () => {
    const w = await setup([row("b", "Food", { folder: "food" })], { folders: ["food"] });
    await w.findAll('[aria-label="Folders"] button').find((b) => b.text() === "food")!.trigger("click");
    await buttonByText(w, "New file")!.trigger("click");
    await flushPromises();
    expect((w.get('input[aria-label="Folder"]').element as HTMLInputElement).value).toBe("food");
    await title(w).setValue("  Rice ");
    await text(w).setValue("Boil it");
    await w.get('input[aria-label="Folder"]').setValue("Food / Grains");
    client.create.mockResolvedValue(full("n", "Rice", "Boil it", { folder: "food/grains" }));
    client.list.mockResolvedValue({ files: [row("n", "Rice", { folder: "food/grains" }), row("b", "Food", { folder: "food" })], folders: ["food", "food/grains"] });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ title: "Rice", body: "Boil it", tags: [], folder: "food/grains" });
    expect(w.text()).toContain("Saved.");
    expect(rows(w)[0]!.text()).toContain("Rice");
  });

  it("a save sends only what changed, with the revision it opened", async () => {
    client.get.mockResolvedValue({ ...full("a", "Tea", "Green"), revision: 4 });
    const w = await setup([row("a", "Tea", { revision: 4 })]);
    await open(w, "a");
    await text(w).setValue("Green and black");
    client.update.mockResolvedValue({ ...full("a", "Tea", "Green and black"), revision: 5 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenCalledExactlyOnceWith("a", { body: "Green and black" }, 4);
    expect(w.text()).toContain("Saved.");
    expect(w.find(".unsaved").exists()).toBe(false);
  });

  it("the agent switch is saved as agent_editable", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await w.get('input[type="checkbox"]').setValue(true);
    client.update.mockResolvedValue({ ...full("a", "Tea"), agent_editable: true, revision: 2 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenCalledExactlyOnceWith("a", { agent_editable: true }, 1);
  });

  it("a refused save offers the newer version or saving over it", async () => {
    client.get.mockResolvedValueOnce(full("a", "Tea", "Mine v1"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Mine v2");
    client.update.mockRejectedValueOnce(new ApiError(412, "This file changed since you opened it."));
    client.get.mockResolvedValueOnce({ ...full("a", "Tea", "Theirs", { last_editor: "agent" }), revision: 7 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(w.get(".conflict").text()).toContain("An agent changed this file after you opened it.");
    client.update.mockResolvedValueOnce({ ...full("a", "Tea", "Mine v2"), revision: 8 });
    await buttonByText(w, "Save mine anyway")!.trigger("click");
    await flushPromises();
    expect(client.update).toHaveBeenLastCalledWith("a", { body: "Mine v2" }, 7);
    expect(w.find(".conflict").exists()).toBe(false);
  });

  it("showing their version drops the user's edits", async () => {
    client.get.mockResolvedValueOnce(full("a", "Tea", "Mine v1"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Mine v2");
    client.update.mockRejectedValueOnce(new ApiError(412, "This file changed since you opened it."));
    client.get.mockResolvedValueOnce({ ...full("a", "Tea", "Theirs"), revision: 3 });
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    await buttonByText(w, "Show their version (drops my changes)")!.trigger("click");
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Theirs");
    expect(w.find(".conflict").exists()).toBe(false);
  });

  it("another failure shows the server's reason and keeps the edits", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await w.get('input[aria-label="Folder"]').setValue("reserved");
    await text(w).setValue("More");
    client.update.mockRejectedValue(new ApiError(422, "That folder name is reserved."));
    await buttonByText(w, "Save")!.trigger("click");
    await flushPromises();
    expect(w.get(".form-error").text()).toBe("That folder name is reserved.");
    expect((text(w).element as HTMLTextAreaElement).value).toBe("More");
  });

  it("a folder the server would refuse keeps Save off and says why", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await w.get('input[aria-label="Folder"]').setValue("a/b/c/d");
    expect(buttonByText(w, "Save")!.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("A folder is up to 3 levels");
  });

  it("an agent's file shows the warning, and restore asks first and waits for a clean editor", async () => {
    const agent = { source: "automatic", last_editor: "user", edited: true, warning: "Written by an agent. Editing it may break the agent that uses it." } as const;
    client.get.mockResolvedValue({ ...full("a", "Plan", "Steps", agent), revision: 3 });
    const w = await setup([row("a", "Plan", { ...agent, revision: 3 })]);
    await open(w, "a");
    expect(w.get('[data-test="agent-warning"]').text()).toContain("may break the agent that uses it");
    await text(w).setValue("Changed");
    expect(buttonByText(w, "Restore original")!.attributes("disabled")).toBeDefined();
    await text(w).setValue("Steps");
    expect(buttonByText(w, "Restore original")!.attributes("disabled")).toBeUndefined();
    await buttonByText(w, "Restore original")!.trigger("click");
    await flushPromises();
    client.revert.mockResolvedValue({ ...full("a", "Plan", "Original steps", { ...agent, edited: false }), revision: 4 });
    confirm()!.click();
    await flushPromises();
    expect(client.revert).toHaveBeenCalledExactlyOnceWith("a", 3);
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Original steps");
    expect(w.text()).toContain("Original text restored.");
  });

  it("deleting asks first, then removes the file and shows the list", async () => {
    client.get.mockResolvedValue(full("a", "Tea"));
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    await open(w, "a");
    await buttonByText(w, "Delete this file")!.trigger("click");
    await flushPromises();
    expect(client.remove).not.toHaveBeenCalled();
    client.remove.mockResolvedValue(undefined);
    client.list.mockResolvedValue({ files: [row("b", "Plan")], folders: [] });
    confirm()!.click();
    await flushPromises();
    expect(client.remove).toHaveBeenCalledExactlyOnceWith("a");
    expect(w.text()).toContain("File deleted.");
    expect(rows(w)).toHaveLength(1);
    expect(w.find('input[aria-label="Title"]').exists()).toBe(false);
  });

  it("switching file with unsaved edits asks first", async () => {
    client.get.mockImplementation(async (id: string) => full(id, id === "a" ? "Tea" : "Plan", "Body"));
    const w = await setup([row("a", "Tea"), row("b", "Plan")]);
    await open(w, "a");
    await text(w).setValue("Edited");
    await w.get('[data-file-id="b"]').trigger("click");
    await flushPromises();
    expect(client.get).toHaveBeenCalledTimes(1);
    expect(document.body.querySelector("dialog[open]")!.textContent).toContain("Discard your changes?");
    cancel()!.click();
    await flushPromises();
    expect((text(w).element as HTMLTextAreaElement).value).toBe("Edited");
    await w.get('[data-file-id="b"]').trigger("click");
    await flushPromises();
    confirm()!.click();
    await flushPromises();
    expect((title(w).element as HTMLInputElement).value).toBe("Plan");
  });

  it("a failed load shows the reason with a way to try again", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().account = makeAccount();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    client.summary.mockResolvedValue(SUMMARY);
    wrapper = mount(NotesView, { attachTo: document.body, global: { plugins: [pinia] } });
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Storage is unavailable");
    client.list.mockResolvedValue({ files: [row("a", "Tea")], folders: [] });
    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect(rows(wrapper)).toHaveLength(1);
  });

  it("ignores an open reply from a previous account", async () => {
    let finish!: (file: BrainFile) => void;
    client.get.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    useAuthStore().account = null;
    client.list.mockResolvedValue({ files: [], folders: [] });
    useAuthStore().account = makeAccount();
    finish(full("a", "Tea", "Private text"));
    await flushPromises();
    expect(w.find('textarea[aria-label="File text"]').exists()).toBe(false);
    expect(rows(w)).toHaveLength(0);
  });

  it("drops a pending save when the account changes", async () => {
    let finish!: (file: BrainFile) => void;
    client.get.mockResolvedValueOnce(full("a", "Tea"));
    client.update.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const w = await setup([row("a", "Tea")]);
    await open(w, "a");
    await text(w).setValue("Private draft");
    await buttonByText(w, "Save")!.trigger("click");
    expect(client.update).toHaveBeenCalledTimes(1);
    useAuthStore().account = null;
    client.list.mockResolvedValue({ files: [], folders: [] });
    useAuthStore().account = makeAccount();
    finish(full("a", "Tea", "Private draft"));
    await flushPromises();
    expect(w.find('textarea[aria-label="File text"]').exists()).toBe(false);
    expect(w.text()).not.toContain("Saved.");
    expect(rows(w)).toHaveLength(0);
  });

  it("drops an older search reply while a new query is being typed", async () => {
    let finish!: (result: { results: SearchHit[] }) => void;
    client.search.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const w = await setup([row("a", "Tea")]);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const input = w.get('input[aria-label="Search files"]');
    await input.setValue("first");
    await vi.advanceTimersByTimeAsync(300);
    await input.setValue("second");
    finish({ results: [{ ...row("a", "Tea"), score: 2, snippet: "Old result" }] });
    await flushPromises();
    expect(w.text()).not.toContain("Old result");
  });

  it("drops the files from memory when the page goes away", async () => {
    const w = await setup([row("a", "Tea")]);
    const store = useBrainStore();
    expect(store.files).toHaveLength(1);
    w.unmount();
    wrapper = null;
    expect(store.files).toEqual([]);
  });
});
