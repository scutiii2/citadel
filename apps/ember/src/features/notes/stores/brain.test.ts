import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { brainClient, type BrainFile, type BrainFileRow, type BrainSummary, type SearchHit } from "../api/BrainClient";
import { useBrainStore } from "./brain";

vi.mock("../api/BrainClient", () => ({
  brainClient: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), revert: vi.fn(), remove: vi.fn(), search: vi.fn(), summary: vi.fn() },
}));

const client = vi.mocked(brainClient);

const row = (id: string, title = `file ${id}`, folder = ""): BrainFileRow => ({
  id, title, folder, tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", chars: 5, warning: null, shared_from: "",
});
const file = (id: string, title = `file ${id}`, body = "text", folder = ""): BrainFile => {
  const { chars: _chars, ...rest } = row(id, title, folder);
  return { ...rest, body };
};
const SUMMARY: BrainSummary = { files: 2, bytes: 1200, skipped: 0, max_files: 500, max_total_bytes: 5_000_000, max_record_chars: 20_000 };
const hit = (id: string): SearchHit => ({ ...row(id), score: 1, snippet: "…" });

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useBrainStore() };
}

const later = <T>() => {
  let done!: (value: T) => void;
  const promise = new Promise<T>((resolve) => { done = resolve; });
  return { promise, done };
};

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue({ files: [row("a"), row("b")], folders: ["x"] });
  client.summary.mockResolvedValue(SUMMARY);
});

describe("load", () => {
  it("shows the server's files, folders and quota", async () => {
    const { store } = setup();
    expect(store.status).toBe("idle");
    const loading = store.load();
    expect(store.status).toBe("loading");
    await loading;
    expect(store.status).toBe("ready");
    expect(store.files.map((f) => f.id)).toEqual(["a", "b"]);
    expect(store.folders).toEqual(["x"]);
    expect(store.summary).toEqual(SUMMARY);
  });

  it("does nothing without an account", async () => {
    const { auth, store } = setup();
    auth.account = null;
    await store.load();
    expect(client.list).not.toHaveBeenCalled();
  });

  it("still shows the list when only the quota fails", async () => {
    const { store } = setup();
    client.summary.mockRejectedValue(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.summary).toBeNull();
  });

  it("a first failure is an error state with the server's text; a later one keeps the list", async () => {
    const { store } = setup();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("error");
    expect(store.error).toBe("Storage is unavailable");
    await store.load();
    expect(store.status).toBe("ready");
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.files).toHaveLength(2);
    expect(store.error).toBe("Storage is unavailable");
  });

  it("a newer load wins over an older reply that arrives late", async () => {
    const { store } = setup();
    const slow = later<{ files: BrainFileRow[]; folders: string[] }>();
    client.list.mockReturnValueOnce(slow.promise);
    const first = store.load();
    client.list.mockResolvedValueOnce({ files: [row("new")], folders: [] });
    await store.load();
    slow.done({ files: [row("old")], folders: [] });
    await first;
    expect(store.files.map((f) => f.id)).toEqual(["new"]);
  });

  it("a reply that arrives after forget shows nothing", async () => {
    const { store } = setup();
    const slow = later<{ files: BrainFileRow[]; folders: string[] }>();
    client.list.mockReturnValueOnce(slow.promise);
    const loading = store.load();
    store.forget();
    slow.done({ files: [row("late")], folders: [] });
    await loading;
    expect(store.files).toEqual([]);
    expect(store.status).toBe("idle");
  });
});

describe("search", () => {
  it("shows the hits, and an empty query clears them", async () => {
    const { store } = setup();
    client.search.mockResolvedValue({ results: [hit("a")] });
    await store.search("  tea ");
    expect(client.search).toHaveBeenCalledExactlyOnceWith("tea");
    expect(store.hits?.map((h) => h.id)).toEqual(["a"]);
    await store.search("   ");
    expect(store.hits).toBeNull();
    expect(client.search).toHaveBeenCalledTimes(1);
  });

  it("ignores an older search that answers last", async () => {
    const { store } = setup();
    const slow = later<{ results: SearchHit[] }>();
    client.search.mockReturnValueOnce(slow.promise);
    const first = store.search("old");
    client.search.mockResolvedValueOnce({ results: [hit("new")] });
    await store.search("new");
    slow.done({ results: [hit("old")] });
    await first;
    expect(store.hits?.map((h) => h.id)).toEqual(["new"]);
    expect(store.searching).toBe(false);
  });

  it("a failed search shows the reason and falls back to no hits", async () => {
    const { store } = setup();
    client.search.mockRejectedValue(new ApiError(422, "Invalid brain request."));
    await store.search("x");
    expect(store.hits).toBeNull();
    expect(store.searchError).toBe("Invalid brain request.");
    expect(store.searching).toBe(false);
  });

  it("clearSearch drops hits and a search still on its way", async () => {
    const { store } = setup();
    const slow = later<{ results: SearchHit[] }>();
    client.search.mockReturnValueOnce(slow.promise);
    const searching = store.search("x");
    store.clearSearch();
    slow.done({ results: [hit("a")] });
    await searching;
    expect(store.hits).toBeNull();
    expect(store.searching).toBe(false);
  });
});

describe("changes", () => {
  it("create puts the new file first, looks again, and returns the file", async () => {
    const { store } = setup();
    await store.load();
    client.create.mockResolvedValue(file("c", "Created", "body"));
    client.list.mockResolvedValue({ files: [row("c", "Created"), row("a"), row("b")], folders: ["x", "y"] });
    const draft = { title: "Created", body: "body", tags: [], folder: "y" };
    const made = await store.create(draft);
    expect(client.create).toHaveBeenCalledExactlyOnceWith(draft);
    expect(made.id).toBe("c");
    expect(store.files.map((f) => f.id)).toEqual(["c", "a", "b"]);
    expect(store.folders).toEqual(["x", "y"]);
    expect(client.list).toHaveBeenCalledTimes(2);
  });

  it("save sends the changes and the revision, and moves the file to the top", async () => {
    const { store } = setup();
    await store.load();
    client.update.mockResolvedValue({ ...file("b", "Renamed"), revision: 2 });
    client.list.mockResolvedValue({ files: [row("b", "Renamed"), row("a")], folders: [] });
    const saved = await store.save("b", { title: "Renamed" }, 1);
    expect(client.update).toHaveBeenCalledExactlyOnceWith("b", { title: "Renamed" }, 1);
    expect(saved.revision).toBe(2);
    expect(store.files.map((f) => [f.id, f.title])).toEqual([["b", "Renamed"], ["a", "file a"]]);
  });

  it("a refused save changes nothing and passes the error on", async () => {
    const { store } = setup();
    await store.load();
    client.update.mockRejectedValue(new ApiError(412, "This file changed since you opened it."));
    await expect(store.save("a", { title: "x" }, 1)).rejects.toMatchObject({ status: 412 });
    expect(store.files.map((f) => f.title)).toEqual(["file a", "file b"]);
  });

  it("revert and remove call the server with the revision and update the list", async () => {
    const { store } = setup();
    await store.load();
    client.revert.mockResolvedValue({ ...file("a", "Original"), revision: 3 });
    client.list.mockResolvedValue({ files: [row("a", "Original"), row("b")], folders: [] });
    await store.revert("a", 2);
    expect(client.revert).toHaveBeenCalledExactlyOnceWith("a", 2);
    expect(store.files[0]).toMatchObject({ id: "a", title: "Original" });
    client.remove.mockResolvedValue(undefined);
    client.list.mockResolvedValue({ files: [row("b")], folders: [] });
    await store.remove("a");
    expect(client.remove).toHaveBeenCalledExactlyOnceWith("a");
    expect(store.files.map((f) => f.id)).toEqual(["b"]);
  });

  it("a change that finishes after forget does not bring files back", async () => {
    const { store } = setup();
    await store.load();
    const slow = later<BrainFile>();
    client.update.mockReturnValueOnce(slow.promise);
    const saving = store.save("a", { title: "x" }, 1);
    store.forget();
    slow.done(file("a", "x"));
    await saving;
    await flushPromises();
    expect(store.files).toEqual([]);
  });
});

describe("private data", () => {
  it("signing out clears everything", async () => {
    const { auth, store } = setup();
    client.search.mockResolvedValue({ results: [hit("a")] });
    await store.load();
    await store.search("a");
    auth.account = null;
    expect(store.files).toEqual([]);
    expect(store.folders).toEqual([]);
    expect(store.summary).toBeNull();
    expect(store.hits).toBeNull();
    expect(store.status).toBe("idle");
  });
});
