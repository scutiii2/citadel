import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { BrainFileRow, SearchHit } from "../../notes/api/BrainClient";
import { globalClient } from "../api/GlobalClient";
import GlobalFiles from "./GlobalFiles.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { list: vi.fn(), search: vi.fn(), summary: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));
vi.mock("./GlobalFileDialog.vue", () => ({
  default: {
    props: ["open", "fileId", "canWrite", "maxChars"],
    emits: ["close", "done"],
    template: '<div data-test="file-dialog" :data-id="fileId ?? \'new\'"><button data-test="finish" @click="$emit(\'done\', \'Saved.\')">finish</button></div>',
  },
}));
const client = vi.mocked(globalClient);

const row = (id: string, title: string, extra: Partial<BrainFileRow> = {}): BrainFileRow => ({
  id, title, folder: "", tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-02T00:00:00", chars: 12, warning: null, shared_from: "", ...extra,
});
const hit = (id: string, title: string): SearchHit => ({ ...row(id, title), score: 1, snippet: "…" });

let wrapper: VueWrapper | null = null;
async function mountIt(canWrite = false) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(GlobalFiles, { attachTo: document.body, props: { canWrite }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue({ files: [row("f1", "Style guide", { folder: "team" }), row("f2", "Glossary")], folders: ["team"] });
  client.summary.mockResolvedValue({ files: 2, bytes: 100, skipped: 0, max_files: 500, max_total_bytes: 5_000_000, max_record_chars: 5000, notice: "n" });
  client.search.mockResolvedValue([hit("f2", "Glossary")]);
});
afterEach(() => {
  vi.useRealTimers();
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalFiles", () => {
  it("lists the files and filters by folder", async () => {
    const w = await mountIt();
    expect(w.text()).toContain("Style guide");
    expect(w.text()).toContain("Glossary");
    expect(client.list).toHaveBeenLastCalledWith(undefined);
    await w.findAll("button").find((b) => b.text() === "team")!.trigger("click");
    await flushPromises();
    expect(client.list).toHaveBeenLastCalledWith("team");
  });

  it("says when there are no files", async () => {
    client.list.mockResolvedValue({ files: [], folders: [] });
    const w = await mountIt();
    expect(w.text()).toContain("No files yet.");
  });

  it("searches after a pause, shows the hits, and ignores a late answer for old text", async () => {
    const w = await mountIt();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let finishOld!: (hits: SearchHit[]) => void;
    client.search.mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }));
    await w.find("input[type='search']").setValue("gloss");
    vi.advanceTimersByTime(300);
    client.search.mockResolvedValueOnce([hit("f1", "Style guide")]);
    await w.find("input[type='search']").setValue("style");
    vi.advanceTimersByTime(300);
    await flushPromises();
    finishOld([hit("f2", "Glossary")]);
    await flushPromises();
    expect(client.search).toHaveBeenCalledWith("style");
    expect(w.text()).toContain("Style guide");
    expect(w.text()).not.toContain("Glossary");
    await w.find("input[type='search']").setValue("");
    await flushPromises();
    expect(w.text()).toContain("Glossary");
  });

  it("shows New file only to a writer", async () => {
    expect((await mountIt(false)).text()).not.toContain("New file");
    wrapper?.unmount();
    expect((await mountIt(true)).text()).toContain("New file");
  });

  it("opens the dialog on a row click and reloads with a note after it is done", async () => {
    const w = await mountIt(true);
    await w.find("[data-file-id='f2']").trigger("click");
    expect(w.get("[data-test='file-dialog']").attributes("data-id")).toBe("f2");
    client.list.mockClear();
    await w.get("[data-test='finish']").trigger("click");
    await flushPromises();
    expect(w.find("[data-test='file-dialog']").exists()).toBe(false);
    expect(w.get("[role='status']").text()).toContain("Saved.");
    expect(client.list).toHaveBeenCalled();
  });

  it("shows the error and retries when the list cannot load", async () => {
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    const w = await mountIt();
    expect(w.text()).toContain("Storage is unavailable");
    await w.findAll("button").find((b) => b.text() === "Try again")!.trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Style guide");
  });

  it("clears everything when the account changes and ignores a late reply", async () => {
    const w = await mountIt();
    let late!: (value: { files: BrainFileRow[]; folders: string[] }) => void;
    client.list.mockReturnValueOnce(new Promise((resolve) => { late = resolve; }));
    await w.findAll("button").find((b) => b.text() === "team")!.trigger("click");
    useAuthStore().account = makeAccount({ id: 99, username: "other", email: "o@example.com" });
    late({ files: [row("x", "Leaked")], folders: [] });
    await flushPromises();
    expect(w.text()).not.toContain("Leaked");
    expect(w.text()).not.toContain("Style guide");
  });
});
