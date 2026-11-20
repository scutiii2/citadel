import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { sharingClient, type Block, type Share } from "../api/SharingClient";
import { useSharingStore } from "./sharing";

vi.mock("../api/SharingClient", () => ({
  sharingClient: {
    create: vi.fn(), inbox: vi.fn(), sent: vi.fn(), get: vi.fn(), revoke: vi.fn(), accept: vi.fn(), decline: vi.fn(),
    blocks: vi.fn(), block: vi.fn(), unblock: vi.fn(),
  },
}));

const client = vi.mocked(sharingClient);

const share = (id: string, extra: Partial<Share> = {}): Share => ({
  id, kind: "file", title: `share ${id}`, status: "pending", sender: "bo", recipient: "me",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 5, ...extra,
});
const block = (uid: string): Block => ({ uid, username: `user ${uid}`, created_at: "2026-01-01T00:00:00Z" });

function setup() {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = makeAccount({ username: "u", email: "u@example.com" });
  return { auth, store: useSharingStore() };
}

const later = <T>() => {
  let done!: (value: T) => void;
  const promise = new Promise<T>((resolve) => { done = resolve; });
  return { promise, done };
};

beforeEach(() => {
  vi.clearAllMocks();
  client.inbox.mockResolvedValue([share("a"), share("b")]);
  client.sent.mockResolvedValue([share("s1", { sender: "me", recipient: "bo" })]);
  client.blocks.mockResolvedValue([block("u1")]);
});

describe("load", () => {
  it("shows the inbox, the sent shares and the blocks", async () => {
    const { store } = setup();
    expect(store.status).toBe("idle");
    const loading = store.load();
    expect(store.status).toBe("loading");
    await loading;
    expect(store.status).toBe("ready");
    expect(store.inbox.map((s) => s.id)).toEqual(["a", "b"]);
    expect(store.sent.map((s) => s.id)).toEqual(["s1"]);
    expect(store.blocks.map((b) => b.uid)).toEqual(["u1"]);
  });

  it("does nothing without an account", async () => {
    const { auth, store } = setup();
    auth.account = null;
    await store.load();
    expect(client.inbox).not.toHaveBeenCalled();
  });

  it("a first failure is an error state; a later one keeps the lists", async () => {
    const { store } = setup();
    client.inbox.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("error");
    expect(store.error).toBe("Storage is unavailable");
    await store.load();
    client.sent.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    await store.load();
    expect(store.status).toBe("ready");
    expect(store.inbox).toHaveLength(2);
    expect(store.error).toBe("Storage is unavailable");
  });

  it("a newer load wins over an older reply that arrives late", async () => {
    const { store } = setup();
    const slow = later<Share[]>();
    client.inbox.mockReturnValueOnce(slow.promise);
    const first = store.load();
    client.inbox.mockResolvedValueOnce([share("new")]);
    await store.load();
    slow.done([share("old")]);
    await first;
    expect(store.inbox.map((s) => s.id)).toEqual(["new"]);
  });

  it("a reply that arrives after forget shows nothing", async () => {
    const { store } = setup();
    const slow = later<Share[]>();
    client.inbox.mockReturnValueOnce(slow.promise);
    const loading = store.load();
    store.forget();
    slow.done([share("late")]);
    await loading;
    expect(store.inbox).toEqual([]);
    expect(store.status).toBe("idle");
  });
});

describe("changes", () => {
  it("sends from an editor without loading private lists before the sharing page opens", async () => {
    const { store } = setup();
    client.create.mockResolvedValueOnce(share("n"));
    await store.create({ kind: "file", file_id: "f1", to_global: true });
    expect(client.inbox).not.toHaveBeenCalled();
    expect(store.status).toBe("idle");
  });

  it("create sends the share, returns it and looks again", async () => {
    const { store } = setup();
    await store.load();
    client.create.mockResolvedValue(share("n", { recipient: "bo" }));
    const made = await store.create({ kind: "file", file_id: "f1", recipient: "bo" });
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "file", file_id: "f1", recipient: "bo" });
    expect(made.id).toBe("n");
    expect(client.sent).toHaveBeenCalledTimes(2);
  });

  it("accept passes the landing, decline and revoke pass the id, and each looks again", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockResolvedValue(share("a", { status: "accepted", result_id: "f9" }));
    client.decline.mockResolvedValue(share("b", { status: "declined" }));
    client.revoke.mockResolvedValue(share("s1", { status: "revoked" }));
    expect((await store.accept("a", { title: "Tea", folder: "shared" })).result_id).toBe("f9");
    await store.decline("b");
    await store.revoke("s1");
    expect(client.accept).toHaveBeenCalledExactlyOnceWith("a", { title: "Tea", folder: "shared" });
    expect(client.decline).toHaveBeenCalledExactlyOnceWith("b");
    expect(client.revoke).toHaveBeenCalledExactlyOnceWith("s1");
    expect(client.inbox).toHaveBeenCalledTimes(4);
  });

  it("a refused change passes the server's reason on and changes nothing", async () => {
    const { store } = setup();
    await store.load();
    client.accept.mockRejectedValue(new ApiError(409, "You have reached the limit of 500 files."));
    await expect(store.accept("a", {})).rejects.toMatchObject({ status: 409, message: "You have reached the limit of 500 files." });
    expect(store.inbox).toHaveLength(2);
    expect(client.inbox).toHaveBeenCalledTimes(1);
  });

  it("block and unblock call the server and look again", async () => {
    const { store } = setup();
    await store.load();
    client.block.mockResolvedValue([block("u1"), block("u2")]);
    await store.block("bo");
    expect(client.block).toHaveBeenCalledExactlyOnceWith("bo");
    client.unblock.mockResolvedValue(undefined);
    await store.unblock("u2");
    expect(client.unblock).toHaveBeenCalledExactlyOnceWith("u2");
    expect(client.blocks).toHaveBeenCalledTimes(3);
  });

  it("a change that finishes after forget does not bring the lists back", async () => {
    const { store } = setup();
    await store.load();
    const slow = later<Share>();
    client.decline.mockReturnValueOnce(slow.promise);
    const declining = store.decline("a");
    store.forget();
    slow.done(share("a", { status: "declined" }));
    await declining;
    expect(store.inbox).toEqual([]);
    expect(client.inbox).toHaveBeenCalledTimes(1);
  });
});

describe("private data", () => {
  it("signing out clears everything", async () => {
    const { auth, store } = setup();
    await store.load();
    auth.account = null;
    expect(store.inbox).toEqual([]);
    expect(store.sent).toEqual([]);
    expect(store.blocks).toEqual([]);
    expect(store.status).toBe("idle");
  });
});
