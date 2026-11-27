import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import type { ChatMessage } from "../../../api/types";
import { useQuestionRetry } from "./useQuestionRetry";

const FOUR: ChatMessage[] = [
  { role: "user", content: "q1" }, { role: "assistant", content: "a1" },
  { role: "user", content: "q2" }, { role: "assistant", content: "a2" },
];

function setup() {
  const activeId = ref<string | null>("c1");
  const messages = ref<ChatMessage[]>([...FOUR]);
  const composer = { isEmpty: vi.fn(() => true), restore: vi.fn(), clear: vi.fn() };
  const retry = useQuestionRetry({ activeId, messages }, () => composer);
  const shown = () => retry.shown.value.map((m) => m.content);
  return { activeId, messages, composer, retry, shown };
}

describe("retrying the last question", () => {
  it("moves the question into the message box and hides it and its answer, changing nothing yet", () => {
    const { composer, retry, shown, messages } = setup();

    expect(retry.start(2)).toBe(true);

    expect(composer.restore).toHaveBeenCalledWith("q2");
    expect(retry.active.value).toBe(true);
    expect(shown()).toEqual(["q1", "a1"]);
    expect(messages.value).toHaveLength(4);
  });

  it("is refused while something else is in the message box", () => {
    const { composer, retry, shown } = setup();
    composer.isEmpty.mockReturnValue(false);

    expect(retry.start(2)).toBe(false);

    expect(composer.restore).not.toHaveBeenCalled();
    expect(shown()).toHaveLength(4);
  });

  it("cancelling empties the box and shows the exchange again", () => {
    const { composer, retry, shown } = setup();
    retry.start(2);

    retry.cancel();

    expect(composer.clear).toHaveBeenCalled();
    expect(shown()).toHaveLength(4);
  });

  it("sending replaces the question from where it stood", async () => {
    const { retry } = setup();
    const send = vi.fn(async () => true);
    retry.start(2);

    expect(await retry.resend("q2 again", send)).toBe(true);

    expect(send).toHaveBeenCalledWith("q2 again", { truncateTo: 2 });
    expect(retry.active.value).toBe(false);
  });

  it("stays pending when the question is not taken", async () => {
    const { retry, shown } = setup();
    retry.start(2);

    expect(await retry.resend("q2 again", async () => false)).toBe(false);

    expect(retry.active.value).toBe(true);
    expect(shown()).toEqual(["q1", "a1"]);
  });

  it.each<[string, (s: ReturnType<typeof setup>) => void]>([
    ["another chat is opened", (s) => { s.activeId.value = "c2"; }],
    ["the chat gains a message", (s) => { s.messages.value = [...s.messages.value, { role: "user", content: "x" }]; }],
  ])("is cancelled when %s", async (_name, change) => {
    const state = setup();
    state.retry.start(2);

    change(state);
    await nextTick();

    expect(state.retry.active.value).toBe(false);
    expect(state.composer.clear).toHaveBeenCalled();
  });

  it("can be forgotten without touching the box", () => {
    const { composer, retry } = setup();
    retry.start(2);

    retry.forget();

    expect(retry.active.value).toBe(false);
    expect(composer.clear).not.toHaveBeenCalled();
  });
});
