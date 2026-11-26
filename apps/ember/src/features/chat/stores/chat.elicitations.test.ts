import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { chatsClient, type ChatSummary } from "../api/ChatsClient";
import { ApiError } from "../../../api/http";
import type { ChatMessage, TurnEvent } from "../../../api/types";
import { watchTurn, type WatchEnd } from "../services/turnStream";
import { useAuthStore } from "../../../stores/auth";
import { useChatStore } from "./chat";

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
    append: vi.fn(),
    branch: vi.fn(),
    suggestion: vi.fn(),
    answerElicitation: vi.fn(),
  },
}));
vi.mock("../services/turnStream", () => ({ watchTurn: vi.fn() }));
vi.mock("../composables/useNotify", () => ({ chimeIfAway: vi.fn() }));
vi.mock("../services/slashCommands", () => ({
  SlashCommandRunner: class {
    run = vi.fn();
    list = vi.fn(async () => []);
    schemaFor = vi.fn(async () => null);
  },
}));

const client = vi.mocked(chatsClient);
const watch = vi.mocked(watchTurn);

const ACCOUNT = {
  id: 1,
  username: "root",
  email: "root@example.com",
  email_verified: true,
  roles: [],
  permissions: ["chat.use", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"],
};

const summary = (id: string, count = 0, running = false): ChatSummary => ({
  id,
  title: `Chat ${id}`,
  agent_id: "a1",
  message_count: count,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  running,
});

const TWO: ChatMessage[] = [
  { role: "user", content: "q1" },
  { role: "assistant", content: "a1" },
];

let emit: (event: TurnEvent) => void = () => {
  throw new Error("no answer is being watched");
};
const fire = (event: Record<string, unknown>) => emit({ sequence: 1, ...event } as TurnEvent);

async function storeWith(chats: Record<string, ChatMessage[]>, running: string[] = []) {
  setActivePinia(createPinia());
  useAuthStore().account = ACCOUNT;
  client.list.mockResolvedValue(Object.entries(chats).map(([id, m]) => summary(id, m.length, running.includes(id))));
  client.get.mockImplementation(async (id: string) => ({
    ...summary(id, chats[id]!.length, running.includes(id)),
    messages: structuredClone(chats[id]!),
  }));
  const chat = useChatStore();
  await flushPromises();
  return chat;
}

/** A chat whose answer is being written. */
async function running(chats: Record<string, ChatMessage[]> = { c1: TWO }) {
  const chat = await storeWith(chats);
  await chat.selectChat("c1");
  await chat.send("ask something");
  return chat;
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  watch.mockImplementation(
    (_id, _after, onEvent) =>
      new Promise<WatchEnd>(() => {
        emit = onEvent;
      }),
  );
  client.startTurn.mockResolvedValue({ chat: { ...summary("c1", 2, true) }, sequence: 5 });
  client.append.mockResolvedValue(undefined as never);
  client.search.mockResolvedValue([]);
  client.suggestion.mockResolvedValue({ text: null });
});

const CARD = { id: "e1", server: "Notes", tool: "save", mode: "form", message: "Folder?", fields: [] };
const ask = () => fire({ type: "elicitation_request", ...CARD });

describe("an outside server's question", () => {
  it("is asked for with every turn", async () => {
    await running();

    expect(client.startTurn.mock.calls[0]![1]).toMatchObject({ can_elicit: true });
  });

  it("appears once and comes back from a snapshot", async () => {
    const chat = await running();
    ask();
    ask();
    expect(chat.pendingElicitations).toEqual([CARD]);

    fire({ type: "snapshot", text: "", activity: "", elicitations: [CARD] });

    expect(chat.pendingElicitations).toEqual([CARD]);
  });

  it("stays with its buttons off until the agent confirms", async () => {
    const chat = await running();
    ask();
    client.answerElicitation.mockResolvedValue({ answered: true });

    await chat.answerElicitation("e1", "accept", { folder: "Work" });
    await chat.answerElicitation("e1", "decline");

    expect(client.answerElicitation).toHaveBeenCalledOnce();
    expect(client.answerElicitation).toHaveBeenCalledWith("c1", "e1", "accept", { folder: "Work" });
    expect(chat.answeringElicitations).toEqual(["e1"]);
    fire({ type: "elicitation_resolved", id: "e1", outcome: "accepted" });
    expect(chat.pendingElicitations).toEqual([]);
    expect(chat.answeringElicitations).toEqual([]);
  });

  it("keeps the card and says why an answer was refused", async () => {
    const chat = await running();
    ask();
    client.answerElicitation.mockRejectedValue(new ApiError(422, "Folder: this field is required."));

    await chat.answerElicitation("e1", "accept", {});

    expect(chat.pendingElicitations).toHaveLength(1);
    expect(chat.answeringElicitations).toEqual([]);
    expect(chat.elicitationProblems).toEqual({ e1: "Folder: this field is required." });
    expect(chat.sendError).toBe("");
  });

  it("is dropped quietly when nothing is waiting any more", async () => {
    const chat = await running();
    ask();
    client.answerElicitation.mockRejectedValue(new ApiError(409, "Nothing is waiting for that answer"));

    await chat.answerElicitation("e1", "cancel");

    expect(chat.pendingElicitations).toEqual([]);
  });
});
