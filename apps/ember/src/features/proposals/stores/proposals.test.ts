import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { proposalsClient, type Proposal } from "../api/ProposalsClient";
import { useProposalsStore } from "./proposals";

vi.mock("../api/ProposalsClient", () => ({
  proposalsClient: { list: vi.fn(), get: vi.fn(), accept: vi.fn(), decline: vi.fn() },
}));
const client = vi.mocked(proposalsClient);

const proposal = (id: string): Proposal => ({
  id, title: `suggestion ${id}`, folder: "", tags: [], chat_id: "c1", item_ids: [1], status: "pending",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 5,
});

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useProposalsStore() };
}
const later = <T>() => {
  let done!: (value: T) => void;
  const promise = new Promise<T>((resolve) => { done = resolve; });
  return { promise, done };
};

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue([proposal("a"), proposal("b")]);
});

describe("load", () => {
  it("shows the waiting suggestions", async () => {
    const { store } = setup();
    expect(store.status).toBe("idle");
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.items.map((p) => p.id)).toEqual(["a", "b"]);
  });

  it("does nothing without an account", async () => {
    const { auth, store } = setup();
    auth.account = null;
    await store.load();
    expect(client.list).not.toHaveBeenCalled();
  });

  it("keeps the list when a refresh fails, and shows the error when the first load fails", async () => {
    const { store } = setup();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect([store.status, store.error]).toEqual(["error", "Storage is unavailable"]);
    await store.load();
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.items).toHaveLength(2);
  });

  it("ignores an older reply that arrives after a newer one", async () => {
    const { store } = setup();
    const first = later<Proposal[]>();
    client.list.mockReturnValueOnce(first.promise);
    const slow = store.load();
    client.list.mockResolvedValueOnce([proposal("new")]);
    await store.load();
    first.done([proposal("old")]);
    await slow;
    expect(store.items.map((p) => p.id)).toEqual(["new"]);
  });
});

describe("changes", () => {
  it("refreshes the list after a keep or a decline", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockResolvedValue({ ...proposal("a"), status: "accepted", removed: 1 });
    client.list.mockResolvedValue([proposal("b")]);
    const done = await store.accept("a", { remove_items: true });
    expect(done.removed).toBe(1);
    expect(client.accept).toHaveBeenCalledWith("a", { remove_items: true });
    expect(store.items.map((p) => p.id)).toEqual(["b"]);
    client.decline.mockResolvedValue({ ...proposal("b"), status: "declined" });
    client.list.mockResolvedValue([]);
    await store.decline("b");
    expect(store.items).toEqual([]);
  });

  it("removes a confirmed decision when the refresh fails", async () => {
    const { store } = setup();
    await store.load();
    client.decline.mockResolvedValue({ ...proposal("a"), status: "declined" });
    client.list.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.decline("a");
    expect(store.items.map((p) => p.id)).toEqual(["b"]);
  });

  it("refreshes when the suggestion was already decided, and still throws", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockRejectedValue(new ApiError(409, "That suggestion is already decided."));
    client.list.mockResolvedValue([proposal("b")]);
    await expect(store.accept("a")).rejects.toThrow("already decided");
    expect(store.items.map((p) => p.id)).toEqual(["b"]);
  });
});

describe("private data", () => {
  it("is dropped by forget and by a change of account, and a late reply is ignored", async () => {
    const { auth, store } = setup();
    await store.load();
    store.forget();
    expect([store.status, store.items]).toEqual(["idle", []]);
    const late = later<Proposal[]>();
    client.list.mockReturnValueOnce(late.promise);
    const loading = store.load();
    auth.account = makeAccount({ id: 99, username: "other", email: "o@example.com" });
    late.done([proposal("x")]);
    await loading;
    expect(store.items).toEqual([]);
  });
});
