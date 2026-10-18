import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { forgeClient, type ForgeGroup, type ForgeWorker } from "../api/ForgeClient";
import { watchGroup } from "../services/forgeStream";
import { useAuthStore } from "./auth";
import { useForgeStore } from "./forge";

vi.mock("../api/ForgeClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/ForgeClient")>()),
  forgeClient: {
    plans: vi.fn(), setPlans: vi.fn(), workers: vi.fn(), createWorker: vi.fn(), removeWorker: vi.fn(),
    groups: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), removeGroup: vi.fn(),
    invite: vi.fn(), removeMember: vi.fn(), send: vi.fn(), answerPermission: vi.fn(), stop: vi.fn(),
  },
}));
vi.mock("../services/forgeStream", () => ({ watchGroup: vi.fn() }));

const client = vi.mocked(forgeClient);
const watch = vi.mocked(watchGroup);

const ACCOUNT = { id: 1, username: "u", email: "u@example.com", email_verified: true, roles: [], permissions: ["forge.use"] };
const worker = (id: number, label = "claude"): ForgeWorker => ({
  id, provider: "claude", label, reported_plan: "Max", online: true, eligible: true, problem: null, last_seen: null, created_at: "2026-10-18T10:00:00",
});
const group = (id: number, extra: Partial<ForgeGroup> = {}): ForgeGroup => ({
  id, title: `G${id}`, mode: "ask", relay: false, running: false, created_at: "2026-10-18T10:00:00", members: [], ...extra,
});

function setup(account: typeof ACCOUNT | null = ACCOUNT) {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = account;
  return { auth, store: useForgeStore() };
}

/** What watchGroup was last asked to do, so a test can feed it events and see it end. */
function lastWatch() {
  const call = watch.mock.calls.at(-1)!;
  return { id: call[0], after: call[1], emit: call[2], signal: call[3] };
}

beforeEach(() => {
  vi.resetAllMocks();
  client.workers.mockResolvedValue([worker(1)]);
  client.groups.mockResolvedValue([group(2), group(3)]);
  client.plans.mockResolvedValue({ claude: ["max"], codex: [] });
  watch.mockImplementation(() => new Promise(() => {}));
});

describe("loading", () => {
  it("loads everything once, together", async () => {
    const { store } = setup();

    await store.ensureLoaded();
    await store.ensureLoaded();

    expect(client.workers).toHaveBeenCalledTimes(1);
    expect(store.workers.map((w) => w.id)).toEqual([1]);
    expect(store.groups.map((g) => g.id)).toEqual([2, 3]);
    expect(store.plans).toEqual({ claude: ["max"], codex: [] });
    expect(store.loading).toBe(false);
  });

  it("does nothing without the forge.use permission", async () => {
    const { store } = setup({ ...ACCOUNT, permissions: ["chat.use"] });

    await store.ensureLoaded();

    expect(client.workers).not.toHaveBeenCalled();
  });

  it("keeps the message when loading fails, and can be retried", async () => {
    const { store } = setup();
    client.groups.mockRejectedValueOnce(new Error("ember_api is down"));

    await store.ensureLoaded();
    expect(store.loadError).toBe("ember_api is down");

    await store.ensureLoaded();
    expect(store.loadError).toBe("");
    expect(store.groups).toHaveLength(2);
  });

  it("drops everything when the account changes", async () => {
    const { auth, store } = setup();
    await store.ensureLoaded();
    store.select(2);

    auth.account = { ...ACCOUNT, id: 9 };
    await flushPromises();

    expect(store.groups).toEqual([]);
    expect(store.selectedId).toBeNull();
    expect(lastWatch().signal.aborted).toBe(true);
  });
});

describe("watching a group", () => {
  it("starts a watch from the beginning and feeds events into the transcript", async () => {
    const { store } = setup();
    await store.ensureLoaded();

    store.select(2);
    const watching = lastWatch();
    watching.emit({ type: "message", seq: 1, sender: "user", kind: "text", body: { text: "hi" }, created_at: "t" });
    watching.emit({ type: "turn", running: true });

    expect([watching.id, watching.after]).toEqual([2, 0]);
    expect(store.connection).toBe("live");
    expect(store.transcript.items).toHaveLength(1);
    expect(store.transcript.running).toBe(true);
  });

  it("stops the old watch and clears the transcript when another group is chosen", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    store.select(2);
    const first = lastWatch();
    first.emit({ type: "message", seq: 1, sender: "user", kind: "text", body: { text: "hi" }, created_at: "t" });

    store.select(3);

    expect(first.signal.aborted).toBe(true);
    expect(store.transcript.items).toEqual([]);
    expect(lastWatch().id).toBe(3);
    first.emit({ type: "message", seq: 2, sender: "user", kind: "text", body: { text: "late" }, created_at: "t" });
    expect(store.transcript.items).toEqual([]);  // an aborted watch is ignored
  });

  it("marks the connection lost when the watch gives up, and reconnect resumes from the cursor", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    watch.mockImplementationOnce(async (_id, _after, emit) => {
      emit({ type: "message", seq: 5, sender: "user", kind: "text", body: { text: "a" }, created_at: "t" });
      throw new Error("Lost the connection to ember_api");
    });

    store.select(2);
    await flushPromises();
    expect(store.connection).toBe("lost");

    store.reconnect();
    expect(lastWatch().after).toBe(5);
    expect(store.connection).toBe("live");
    expect(store.transcript.items).toHaveLength(1);
  });

  it("refreshes the lists and drops the selection when the group is gone", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    watch.mockResolvedValueOnce("gone");
    client.groups.mockResolvedValue([group(3)]);

    store.select(2);
    await flushPromises();

    expect(store.selectedId).toBeNull();
    expect(store.groups.map((g) => g.id)).toEqual([3]);
  });

  it("leave() stops the watch but keeps the selection", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    store.select(2);
    const watching = lastWatch();

    store.leave();

    expect(watching.signal.aborted).toBe(true);
    expect(store.selectedId).toBe(2);
    expect(store.connection).toBe("idle");
  });
});

describe("groups", () => {
  it("creates a group, selects it and starts watching it", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    client.createGroup.mockResolvedValue(group(10, { title: "New" }));

    await store.createGroup("New", "plan");

    expect(client.createGroup).toHaveBeenCalledWith("New", "plan");
    expect(store.groups[0]!.id).toBe(10);
    expect(store.selectedId).toBe(10);
    expect(lastWatch().id).toBe(10);
  });

  it("replaces a group with the server's version after an update", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    client.updateGroup.mockResolvedValue(group(2, { mode: "plan", relay: true }));

    await store.updateGroup(2, { mode: "plan", relay: true });

    expect(store.groups.find((g) => g.id === 2)).toMatchObject({ mode: "plan", relay: true });
  });

  it("removes a group and deselects it if it was open", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    store.select(2);
    client.removeGroup.mockResolvedValue(undefined);

    await store.removeGroup(2);

    expect(store.groups.map((g) => g.id)).toEqual([3]);
    expect(store.selectedId).toBeNull();
  });

  it("updates the group after an invite or a member removal", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    const member = { worker_id: 1, label: "claude", provider: "claude" as const, folder: "C:/x", online: true };
    client.invite.mockResolvedValue(group(2, { members: [member] }));
    client.removeMember.mockResolvedValue(group(2));

    await store.invite(2, 1, "C:/x");
    expect(store.groups.find((g) => g.id === 2)!.members).toHaveLength(1);

    await store.removeMember(2, 1);
    expect(store.groups.find((g) => g.id === 2)!.members).toEqual([]);
  });

  it("passes server errors up to the dialog", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    client.invite.mockRejectedValue(new Error("Plan not eligible: Free"));

    await expect(store.invite(2, 1, "C:/x")).rejects.toThrow("Plan not eligible: Free");
  });
});

describe("workers and plans", () => {
  it("returns the token once and keeps only the worker", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    client.createWorker.mockResolvedValue({ ...worker(5, "codex"), provider: "codex", token: "ft_secret" });

    const created = await store.createWorker("codex", "codex");

    expect(created.token).toBe("ft_secret");
    expect(store.workers.map((w) => w.id)).toEqual([1, 5]);
    expect(JSON.stringify(store.workers)).not.toContain("ft_secret");
  });

  it("reloads after removing a worker, since its groups change", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    client.removeWorker.mockResolvedValue(undefined);
    client.workers.mockResolvedValue([]);

    await store.removeWorker(1);

    expect(store.workers).toEqual([]);
    expect(client.groups).toHaveBeenCalledTimes(2);
  });

  it("saves an allowlist and reloads eligibility", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    client.setPlans.mockResolvedValue({ plans: ["max", "pro"] });
    client.plans.mockResolvedValue({ claude: ["max", "pro"], codex: [] });

    await store.savePlans("claude", ["max", "pro"]);

    expect(client.setPlans).toHaveBeenCalledWith("claude", ["max", "pro"]);
    expect(store.plans.claude).toEqual(["max", "pro"]);
    expect(client.workers).toHaveBeenCalledTimes(2);
  });
});

describe("talking", () => {
  it("sends to the open group, answers permissions and stops", async () => {
    const { store } = setup();
    await store.ensureLoaded();
    store.select(2);
    client.send.mockResolvedValue({} as never);
    client.answerPermission.mockResolvedValue({ answered: true });
    client.stop.mockResolvedValue({ stopping: true });

    await store.send("@claude hi");
    await store.answer("r1", true);
    await store.stop();

    expect(client.send).toHaveBeenCalledWith(2, "@claude hi");
    expect(client.answerPermission).toHaveBeenCalledWith(2, "r1", true);
    expect(client.stop).toHaveBeenCalledWith(2);
  });

  it("does nothing with no group open", async () => {
    const { store } = setup();
    await store.ensureLoaded();

    await store.send("hi");
    await store.stop();
    await store.answer("r", true);

    expect(client.send).not.toHaveBeenCalled();
  });
});
