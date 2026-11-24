import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { stackClient, type StackItem, type StackView } from "../api/StackClient";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { useStackStore } from "./stack";

vi.mock("../api/StackClient", () => ({
  stackClient: { view: vi.fn(), add: vi.fn(), setPinned: vi.fn(), remove: vi.fn(), compact: vi.fn() },
}));

const client = vi.mocked(stackClient);

const item = (id: number, text = `item ${id}`, pinned = false): StackItem => ({ id, text, pinned, source: "agent", at: "2026-01-01T00:00:00Z" });
const view = (...items: StackItem[]): StackView => ({ items, used: items.length, limit: 40, warn: false, full: false });

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useStackStore() };
}

beforeEach(() => {
  vi.clearAllMocks();
  client.view.mockResolvedValue(view(item(1), item(2)));
});

describe("load", () => {
  it("shows the server's list", async () => {
    const { store } = setup();
    expect(store.entry("c-1").status).toBe("idle");
    const loading = store.load("c-1");
    expect(store.entry("c-1").status).toBe("loading");
    await loading;
    const shown = store.entry("c-1");
    expect(shown.status).toBe("ready");
    expect(shown.view?.items.map((i) => i.id)).toEqual([1, 2]);
  });

  it("a chat that is not saved yet is missing, not an error", async () => {
    const { store } = setup();
    client.view.mockRejectedValue(new ApiError(404, "No such chat."));
    await store.load("c-1");
    expect(store.entry("c-1")).toMatchObject({ status: "missing", view: null, error: "" });
  });

  it("an error with nothing to show is an error state with the server's text", async () => {
    const { store } = setup();
    client.view.mockRejectedValue(new ApiError(503, "Storage is unavailable"));
    await store.load("c-1");
    expect(store.entry("c-1")).toMatchObject({ status: "error", view: null, error: "Storage is unavailable" });
  });

  it("a refresh that fails keeps the list on screen and says so", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.view.mockRejectedValue(new ApiError(503, "Storage is unavailable"));
    await store.load("c-1");
    const shown = store.entry("c-1");
    expect(shown.status).toBe("ready");
    expect(shown.view?.items).toHaveLength(2);
    expect(shown.error).toBe("Storage is unavailable");
  });

  it("drops a late reply when a newer load has started", async () => {
    const { store } = setup();
    let first!: (v: StackView) => void;
    client.view.mockImplementationOnce(() => new Promise<StackView>((resolve) => { first = resolve; }));
    const slow = store.load("c-1");
    client.view.mockResolvedValueOnce(view(item(9, "newer")));
    await store.load("c-1");
    first(view(item(1, "older")));
    await slow;
    expect(store.entry("c-1").view?.items.map((i) => i.text)).toEqual(["newer"]);
  });

  it("a reply that arrives after forget is not shown", async () => {
    const { store } = setup();
    let reply!: (v: StackView) => void;
    client.view.mockImplementationOnce(() => new Promise<StackView>((resolve) => { reply = resolve; }));
    const pending = store.load("c-1");
    store.forget("c-1");
    reply(view(item(1, "private")));
    await pending;
    expect(store.entry("c-1")).toMatchObject({ status: "idle", view: null });
  });
});

describe("changes", () => {
  it("add waits for the server, then shows the reloaded list", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.add.mockResolvedValue(item(3, "new"));
    client.view.mockResolvedValue(view(item(1), item(2), item(3, "new")));
    expect(await store.add("c-1", "new")).toBe(true);
    expect(client.add).toHaveBeenCalledWith("c-1", "new");
    expect(store.entry("c-1").view?.items).toHaveLength(3);
    expect(store.entry("c-1").pending).toBe(false);
  });

  it("a refused add keeps the list and puts the server's reason beside the field", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.add.mockRejectedValue(new ApiError(422, "An item holds at most 500 characters."));
    expect(await store.add("c-1", "x")).toBe(false);
    const shown = store.entry("c-1");
    expect(shown.addError).toBe("An item holds at most 500 characters.");
    expect(shown.view?.items).toHaveLength(2);
    await store.add("c-1", "y");
    client.add.mockResolvedValue(item(3));
    await store.add("c-1", "ok");
    expect(store.entry("c-1").addError).toBe("");
  });

  it("is pending while it waits", async () => {
    const { store } = setup();
    await store.load("c-1");
    let done!: () => void;
    client.setPinned.mockImplementation(() => new Promise((resolve) => { done = () => resolve(item(1, "x", true)); }));
    const waiting = store.setPinned("c-1", 1, true);
    expect(store.entry("c-1").pending).toBe(true);
    done();
    await waiting;
    expect(store.entry("c-1").pending).toBe(false);
  });

  it("pin and remove reload; a failure shows the reason and keeps the list", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.setPinned.mockResolvedValue(item(1, "x", true));
    client.remove.mockResolvedValue(undefined);
    await store.setPinned("c-1", 1, true);
    await store.remove("c-1", 2);
    expect(client.setPinned).toHaveBeenCalledWith("c-1", 1, true);
    expect(client.remove).toHaveBeenCalledWith("c-1", 2);
    expect(client.view).toHaveBeenCalledTimes(3);
    client.remove.mockRejectedValue(new ApiError(404, "No such item in this stack."));
    await store.remove("c-1", 2);
    expect(store.entry("c-1").error).toBe("No such item in this stack.");
  });
});

describe("compact", () => {
  it("shows the summary result", async () => {
    const { store } = setup();
    await store.load("c-1");
    let done!: (r: StackView & { compacted: boolean; replaced: number }) => void;
    client.compact.mockImplementation(() => new Promise((resolve) => { done = resolve; }));
    const waiting = store.compact("c-1");
    expect(store.entry("c-1").compacting).toBe(true);
    done({ ...view(item(5, "summary")), compacted: true, replaced: 8 });
    await waiting;
    const shown = store.entry("c-1");
    expect(shown).toMatchObject({ compacting: false, notice: "Replaced 8 items with a summary." });
    expect(shown.view?.items.map((i) => i.id)).toEqual([5]);
  });

  it("says so when there was nothing to compact, and uses the singular", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.compact.mockResolvedValue({ ...view(item(1)), compacted: false, replaced: 0 });
    await store.compact("c-1");
    expect(store.entry("c-1").notice).toBe("Nothing to compact.");
    client.compact.mockResolvedValue({ ...view(item(5)), compacted: true, replaced: 1 });
    await store.compact("c-1");
    expect(store.entry("c-1").notice).toBe("Replaced 1 item with a summary.");
  });

  it("a failed compaction shows the server's reason and keeps the list", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.compact.mockRejectedValue(new ApiError(502, "The context summarizer did not answer."));
    await store.compact("c-1");
    const shown = store.entry("c-1");
    expect(shown.error).toBe("The context summarizer did not answer.");
    expect(shown.compacting).toBe(false);
    expect(shown.view?.items).toHaveLength(2);
  });

  it("the next change clears an old notice", async () => {
    const { store } = setup();
    await store.load("c-1");
    client.compact.mockResolvedValue({ ...view(item(5)), compacted: true, replaced: 3 });
    await store.compact("c-1");
    client.remove.mockResolvedValue(undefined);
    await store.remove("c-1", 5);
    expect(store.entry("c-1").notice).toBe("");
  });
});

describe("privacy", () => {
  it("drops a pending reply when the account signs out", async () => {
    const { auth, store } = setup();
    let reply!: (value: StackView) => void;
    client.view.mockImplementationOnce(() => new Promise((resolve) => { reply = resolve; }));
    const pending = store.load("c-1");
    auth.account = null;
    expect(store.entry("c-1").status).toBe("idle");
    reply(view(item(1)));
    await pending;
    expect(store.entry("c-1").view).toBeNull();
  });

  it("forget drops the chat and signing out drops everything", async () => {
    const { auth, store } = setup();
    await store.load("c-1");
    await store.load("c-2");
    store.forget("c-1");
    expect(store.entry("c-1").view).toBeNull();
    expect(store.entry("c-2").view).not.toBeNull();
    auth.account = null;
    await flushPromises();
    expect(store.entry("c-2").view).toBeNull();
  });
});
