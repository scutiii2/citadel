import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { extensionsClient } from "../../capabilities/api/ExtensionsClient";
import { chatsClient } from "../api/ChatsClient";
import { useAuthStore } from "../../../stores/auth";
import { useChatStore } from "./chat";

vi.mock("../../capabilities/api/ExtensionsClient", () => ({ extensionsClient: { list: vi.fn() } }));
vi.mock("../api/ChatsClient", () => ({
  chatsClient: {
    list: vi.fn(),
    get: vi.fn(),
    startTurn: vi.fn(),
    cancel: vi.fn(),
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
vi.mock("../composables/useNotify", () => ({ chimeIfAway: vi.fn() }));
vi.mock("../composables/useCompletionNotify", () => ({ notifyCompletion: vi.fn(), clearCompletionNotifications: vi.fn() }));

const ACCOUNT = {
  id: 1,
  username: "root",
  email: "root@example.com",
  email_verified: true,
  roles: [],
  permissions: ["chat.use", "tools.view", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"],
};
const LIVE_KEY = "ember_web.liveTokens.1";
const PANEL_KEY = "ember_web.contextPanel.1";
const ACCURACY_KEY = "ember_web.contextAccuracy.1";

async function store() {
  setActivePinia(createPinia());
  useAuthStore().account = ACCOUNT;
  const chat = useChatStore();
  await flushPromises();
  return chat;
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(extensionsClient.list).mockResolvedValue([]);
  vi.mocked(chatsClient.list).mockResolvedValue([]);
  vi.mocked(chatsClient.search).mockResolvedValue([]);
});

describe("the context display settings", () => {
  it("default to the live count and the panel on, with the estimate", async () => {
    const chat = await store();

    expect(chat.liveTokens).toBe(true);
    expect(chat.contextPanel).toBe(true);
    expect(chat.contextAccuracy).toBe("estimate");
  });

  it("are remembered per account", async () => {
    const chat = await store();

    chat.setLiveTokens(false);
    chat.setContextPanel(false);
    chat.setContextAccuracy("exact");

    expect(localStorage.getItem(LIVE_KEY)).toBe("0");
    expect(localStorage.getItem(PANEL_KEY)).toBe("0");
    expect(localStorage.getItem(ACCURACY_KEY)).toBe("exact");
  });

  it("are read back on login", async () => {
    localStorage.setItem(LIVE_KEY, "0");
    localStorage.setItem(PANEL_KEY, "0");
    localStorage.setItem(ACCURACY_KEY, "exact");

    const chat = await store();

    expect(chat.liveTokens).toBe(false);
    expect(chat.contextPanel).toBe(false);
    expect(chat.contextAccuracy).toBe("exact");
  });

  it("fall back to their defaults when the stored value is not understood", async () => {
    localStorage.setItem(LIVE_KEY, "garbage");
    localStorage.setItem(PANEL_KEY, "garbage");
    localStorage.setItem(ACCURACY_KEY, "garbage");

    const chat = await store();

    expect(chat.liveTokens).toBe(true);
    expect(chat.contextPanel).toBe(true);
    expect(chat.contextAccuracy).toBe("estimate");
  });

  it("work when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const chat = await store();

    expect(() => chat.setContextAccuracy("exact")).not.toThrow();
    expect(chat.contextAccuracy).toBe("exact");
    vi.restoreAllMocks();
  });
});

describe("what fills the context", () => {
  const PARTS = [
    { id: "system_prompt", label: "System prompt", tokens: 300 },
    { id: "messages", label: "Messages", tokens: 700 },
  ];

  async function openChat(messages: object[]) {
    vi.mocked(chatsClient.list).mockResolvedValue([
      { id: "c1", title: "Chat", agent_id: "a1", message_count: messages.length, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", running: false },
    ]);
    vi.mocked(chatsClient.get).mockResolvedValue({
      id: "c1", title: "Chat", agent_id: "a1", message_count: messages.length, created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", running: false,
      messages,
    } as never);
    const chat = await store();
    await chat.selectChat("c1");
    await flushPromises();
    return chat;
  }

  const answer = (extra: object = {}) => ({ role: "assistant", content: "a", context_tokens: 1000, context_window: 200_000, ...extra });

  it("comes from the last answer that reported a context size", async () => {
    const chat = await openChat([{ role: "user", content: "q" }, answer({ context_breakdown: PARTS })]);

    expect(chat.contextParts).toEqual(PARTS);
    expect(chat.contextUsage).toEqual({ tokens: 1000, window: 200_000 });
  });

  it("says whether the provider counted it", async () => {
    const exact = await openChat([answer({ context_breakdown: PARTS, context_breakdown_exact: true })]);
    expect(exact.contextExact).toBe(true);

    const estimated = await openChat([answer({ context_breakdown: PARTS })]);
    expect(estimated.contextExact).toBe(false);
  });

  it("keeps per-agent prompt costs tied to the same answer and clears them after a summary", async () => {
    const usage = [{ agent: "calc", total_tokens: 5, context_breakdown: PARTS, context_breakdown_exact: true }];
    const chat = await openChat([answer({ agent_usage: usage })]);
    expect(chat.contextAgentUsage).toEqual(usage);
    const summarized = await openChat([answer({ agent_usage: usage }), { role: "assistant", content: "s", kind: "summary" }]);
    expect(summarized.contextAgentUsage).toEqual([]);
    expect((await openChat([answer()])).contextAgentUsage).toEqual([]);
  });

  it("shows the current routed answer's agent costs even without a root context size", async () => {
    const usage = [{ agent: "calc", total_tokens: 5, context_breakdown: PARTS }];
    const routed = { role: "assistant", content: "routed answer", agent_usage: usage };
    const chat = await openChat([answer({ context_breakdown: PARTS }), routed]);
    expect(chat.contextAgentUsage).toEqual(usage);
    expect(chat.contextUsage).toBeNull();
    expect(chat.contextParts).toEqual([]);
    const fresh = await openChat([routed]);
    expect(fresh.contextAgentUsage).toEqual(usage);
  });

  it("is empty for an answer saved before breakdowns existed", async () => {
    const chat = await openChat([{ role: "user", content: "q" }, answer()]);

    expect(chat.contextParts).toEqual([]);
    expect(chat.contextUsage).not.toBeNull();
  });

  it("is empty after a summary, like the context size", async () => {
    const chat = await openChat([answer({ context_breakdown: PARTS }), { role: "assistant", content: "s", kind: "summary" }]);

    expect(chat.contextParts).toEqual([]);
    expect(chat.contextUsage).toBeNull();
  });
});
