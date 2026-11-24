import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, ToolStep } from "../../../api/types";
import MessageList from "./MessageList.vue";

vi.mock("../api/ChatsClient", () => ({ chatsClient: { list: vi.fn().mockResolvedValue([]) } }));
vi.mock("../services/turnStream", () => ({ watchTurn: vi.fn(() => Promise.resolve("aborted")) }));

const FID = "a".repeat(32);
const speak: ToolStep = {
  tool: "bard__tool_bard_speak", label: "Generating speech", arguments: {}, ok: true,
  result: JSON.stringify({ file_id: FID, message: "Speech ready" }),
};

beforeEach(() => setActivePinia(createPinia()));

function mountList(props: Record<string, unknown>) {
  return mount(MessageList, {
    props: { messages: [], streaming: "", activity: "", steps: [], busy: false, canChange: true, ...props },
  });
}

describe("MessageList Bard audio", () => {
  it("shows the player under a saved answer, outside the collapsed tool steps", () => {
    const messages: ChatMessage[] = [
      { role: "user", content: "say hi" },
      { role: "assistant", content: "Done.", steps: [speak] },
    ];
    const wrapper = mountList({ messages });
    const audio = wrapper.get("audio");
    expect(audio.attributes("src")).toBe(`/api/bard/audio/${FID}`);
    expect(audio.element.closest("details")).toBeNull();
  });

  it("shows the player while the answer is still being written", () => {
    const wrapper = mountList({ messages: [{ role: "user", content: "say hi" }], steps: [speak], busy: true });
    expect(wrapper.get("audio").attributes("src")).toBe(`/api/bard/audio/${FID}`);
  });

  it("shows no player when no step spoke", () => {
    const messages: ChatMessage[] = [{ role: "user", content: "hi" }, { role: "assistant", content: "Hello" }];
    expect(mountList({ messages }).find("audio").exists()).toBe(false);
  });
});
