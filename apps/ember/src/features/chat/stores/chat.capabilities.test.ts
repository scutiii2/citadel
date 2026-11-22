import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { chatsClient, type ChatSummary } from "../api/ChatsClient";
import { commandsClient } from "../../../api/tools/CommandsClient";
import { settingsClient } from "../../../api/navigation/SettingsClient";
import { watchTurn } from "../services/turnStream";
import { useAuthStore } from "../../../stores/auth";
import { useChatStore } from "./chat";

vi.mock("../api/ChatsClient", () => ({
  chatsClient: {
    list: vi.fn(),
    get: vi.fn(),
    startTurn: vi.fn(),
    cancel: vi.fn(),
    decide: vi.fn(),
    search: vi.fn(),
    remove: vi.fn(),
  },
}));
vi.mock("../../../api/navigation/SettingsClient", () => ({ settingsClient: { get: vi.fn(), set: vi.fn() } }));
vi.mock("../../../api/tools/CommandsClient", () => ({ commandsClient: { list: vi.fn() } }));
vi.mock("../services/turnStream", () => ({ watchTurn: vi.fn() }));

const client = vi.mocked(chatsClient);
const commands = vi.mocked(commandsClient);

const ACCOUNT = { id: 1, username: "root", email: "root@example.com", email_verified: true, roles: [], permissions: ["chat.use", "tools.view", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"] };

const summary = (id: string): ChatSummary => ({
  id,
  title: `Chat ${id}`,
  agent_id: "a1",
  message_count: 0,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  running: false,
});

async function store() {
  setActivePinia(createPinia());
  vi.mocked(settingsClient.get).mockResolvedValue({ force_tool_approval: false });
  useAuthStore().account = ACCOUNT;
  const chat = useChatStore();
  await flushPromises();
  return chat;
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(watchTurn).mockResolvedValue("aborted");
  client.list.mockResolvedValue([]);
  client.search.mockResolvedValue([]);
  client.startTurn.mockResolvedValue({ chat: { ...summary("c1"), running: true }, sequence: 1 });
  commands.list.mockResolvedValue([]);
});

describe("a question carries no extension state", () => {
  it("sends neither extension ids nor tool switches with a question", async () => {
    const chat = await store();

    await chat.send("hi");

    const body = client.startTurn.mock.calls[0]![1];
    expect(body).not.toHaveProperty("disabled_tools");
    expect(body).not.toHaveProperty("enabled_extensions");
  });
});
