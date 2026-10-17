import { accountCapabilitiesClient } from "../api/AccountCapabilitiesClient";
import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { chatsClient, type ChatSummary } from "../api/ChatsClient";
import type { ChatMessage } from "../api/types";
import { watchTurn } from "../services/turnStream";
import { useAuthStore } from "./auth";
import { useChatStore } from "./chat";

vi.mock("../api/AccountCapabilitiesClient", () => ({
  accountCapabilitiesClient: { get: vi.fn(), set: vi.fn() },
}));
vi.mock("../api/ChatsClient", () => ({
  chatsClient: {
    list: vi.fn(),
    get: vi.fn(),
    startTurn: vi.fn(),
    cancel: vi.fn(),
    decide: vi.fn(),
    search: vi.fn(),
    remove: vi.fn(),
    removeAll: vi.fn(),
    rename: vi.fn(),
    importChats: vi.fn(),
    append: vi.fn(),
    branch: vi.fn(),
  },
}));
vi.mock("../services/turnStream", () => ({ watchTurn: vi.fn() }));

const client = vi.mocked(chatsClient);
const watch = vi.mocked(watchTurn);

const ACCOUNT = { id: 1, username: "root", email: "root@example.com", email_verified: true, roles: [], permissions: ["chat.use", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"] };
const PLAN_KEY = "ember_web.plan.1";
const LEAN_KEY = "ember_web.planLean.1";

const summary = (id: string, count = 0): ChatSummary => ({
  id,
  title: `Chat ${id}`,
  agent_id: "a1",
  message_count: count,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  running: false,
});

const TWO: ChatMessage[] = [
  { role: "user", content: "q1" },
  { role: "assistant", content: "a1" },
];

async function storeWithChat() {
  setActivePinia(createPinia());
  useAuthStore().account = ACCOUNT;
  client.list.mockResolvedValue([summary("c1", TWO.length)]);
  client.get.mockImplementation(async (id: string) => ({ ...summary(id, TWO.length), messages: structuredClone(TWO) }));
  const chat = useChatStore();
  await flushPromises();
  await chat.selectChat("c1");
  return chat;
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(accountCapabilitiesClient.get).mockResolvedValue({ capabilities: [], extensions: [], disabled_tools: [] });
  watch.mockImplementation(async () => "aborted");
  client.startTurn.mockResolvedValue({ chat: { ...summary("c1"), running: true }, sequence: 5 });
  client.search.mockResolvedValue([]);
});

describe("the task checklist settings", () => {
  it("are both on until switched off, and remembered per account", async () => {
    const chat = await storeWithChat();
    expect([chat.plan, chat.planLean]).toEqual([true, true]);

    chat.setPlan(false);
    chat.setPlanLean(false);

    expect(localStorage.getItem(PLAN_KEY)).toBe("0");
    expect(localStorage.getItem(LEAN_KEY)).toBe("0");
    chat.setPlan(true);
    chat.setPlanLean(true);
    expect(localStorage.getItem(PLAN_KEY)).toBe("1");
    expect(localStorage.getItem(LEAN_KEY)).toBe("1");
  });

  it("are read back on login and not shared with another account", async () => {
    localStorage.setItem(PLAN_KEY, "0");
    localStorage.setItem(LEAN_KEY, "0");
    const chat = await storeWithChat();
    expect([chat.plan, chat.planLean]).toEqual([false, false]);

    useAuthStore().account = { ...ACCOUNT, id: 2 };
    await flushPromises();
    expect([chat.plan, chat.planLean]).toEqual([true, true]);
  });
});

describe("what a question sends about the checklist", () => {
  it("sends nothing while both are on", async () => {
    const chat = await storeWithChat();

    await chat.send("hello");

    const body = client.startTurn.mock.calls[0]![1];
    expect(body).not.toHaveProperty("plan");
    expect(body).not.toHaveProperty("plan_lean");
  });

  it("sends only the lean flag when just it is off", async () => {
    const chat = await storeWithChat();
    chat.setPlanLean(false);

    await chat.send("hello");

    const body = client.startTurn.mock.calls[0]![1];
    expect(body).toMatchObject({ plan_lean: false });
    expect(body).not.toHaveProperty("plan");
  });

  it("sends both flags when both are off", async () => {
    const chat = await storeWithChat();
    chat.setPlan(false);
    chat.setPlanLean(false);

    await chat.send("hello");

    expect(client.startTurn.mock.calls[0]![1]).toMatchObject({ plan: false, plan_lean: false });
  });
});


describe("what a question sends about exact context counts", () => {
  it("sends nothing with the estimate, which is the default", async () => {
    const chat = await storeWithChat();

    await chat.send("hello");

    expect(client.startTurn.mock.calls[0]![1]).not.toHaveProperty("exact_context");
  });

  it("asks for exact counts when the panel is on and the accuracy is Exact", async () => {
    const chat = await storeWithChat();
    chat.setContextAccuracy("exact");

    await chat.send("hello");

    expect(client.startTurn.mock.calls[0]![1]).toMatchObject({ exact_context: true });
  });

  it("does not ask for exact counts while the panel is hidden", async () => {
    const chat = await storeWithChat();
    chat.setContextAccuracy("exact");
    chat.setContextPanel(false);

    await chat.send("hello");

    expect(client.startTurn.mock.calls[0]![1]).not.toHaveProperty("exact_context");
  });
});
