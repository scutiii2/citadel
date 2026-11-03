import { chatsClient, type ChatChanges, type ChatSummary } from "../api/ChatsClient";
import { isApiStatus } from "../../../api/http";
import type { ChatMessage, Conversation } from "../../../api/types";
import { parseServerTime } from "../../../utils/time";

/** Where conversations are kept. The chat store depends only on this. One
 * call per change, since the store only ever changes one chat at a time.
 * (New messages arrive through ember_api's turns, not through here.) */
export interface ConversationStorage {
  /** Every chat, newest first, with `messages` not loaded yet. */
  list(): Promise<Conversation[]>;
  /** A chat's transcript, and whether an answer is being written for it. */
  detail(id: string): Promise<{ messages: ChatMessage[]; running: boolean; saveToSecondBrain?: boolean; secondBrainScope?: "instance" | "personal" }>;
  rename(id: string, title: string): Promise<void>;
  /** Moves a chat into a folder (null: out of its folder) and/or pins it. */
  update(id: string, changes: ChatChanges): Promise<void>;
  remove(id: string): Promise<void>;
  removeAll(): Promise<void>;
}

/** ember_api's per-account chat history. */
export class ServerConversationStorage implements ConversationStorage {
  async list(): Promise<Conversation[]> {
    return (await chatsClient.list()).map(fromSummary);
  }

  async detail(id: string): Promise<{ messages: ChatMessage[]; running: boolean; saveToSecondBrain?: boolean; secondBrainScope?: "instance" | "personal" }> {
    const chat = await chatsClient.get(id);
    return { messages: chat.messages, running: chat.running, saveToSecondBrain: chat.save_to_second_brain ?? false, secondBrainScope: chat.second_brain_scope ?? "instance" };
  }

  async rename(id: string, title: string): Promise<void> {
    await ignoreMissing(chatsClient.rename(id, title));
  }

  async update(id: string, changes: ChatChanges): Promise<void> {
    await ignoreMissing(chatsClient.update(id, changes));
  }

  async remove(id: string): Promise<void> {
    await ignoreMissing(chatsClient.remove(id));
  }

  async removeAll(): Promise<void> {
    await chatsClient.removeAll();
  }
}

/** A chat that was never saved (deleted before its first write reached the
 * server) or is already gone: nothing left to do. */
async function ignoreMissing(request: Promise<unknown>): Promise<void> {
  try {
    await request;
  } catch (err) {
    if (!isApiStatus(err, 404)) throw err;
  }
}

function fromSummary(s: ChatSummary): Conversation {
  return {
    id: s.id,
    title: s.title,
    messages: [],
    messagesLoaded: false,
    messageCount: s.message_count,
    running: s.running,
    folderId: s.folder_id ?? null,
    pinned: s.pinned ?? false,
    saveToSecondBrain: s.save_to_second_brain ?? false,
    secondBrainScope: s.second_brain_scope ?? "instance",
    agentId: s.agent_id ?? undefined,
    createdAt: parseServerTime(s.created_at),
    updatedAt: parseServerTime(s.updated_at),
  };
}
