import { computed, ref, watch, type Ref } from "vue";
import type { ChatMessage } from "../../../api/types";

/** What retrying needs of the message box. */
export interface RetryComposer {
  isEmpty(): boolean;
  restore(question: string): void;
  clear(): void;
}

/** "Retry": the last question goes back into the message box, with its files, and it and its answer are hidden.
 * Nothing is dropped until it is sent again; cancelling, or leaving the chat, shows them as they were. */
export function useQuestionRetry(
  chat: { activeId: Ref<string | null>; messages: Ref<ChatMessage[]> },
  composer: () => RetryComposer | null,
) {
  // `length` notices messages added under a pending retry, which sending it would drop.
  const pending = ref<{ chatId: string | null; index: number; length: number } | null>(null);
  const active = computed(() => pending.value !== null);
  const shown = computed(() =>
    pending.value?.chatId === chat.activeId.value ? chat.messages.value.slice(0, pending.value.index) : chat.messages.value,
  );

  /** False when the box holds something else, which this must not overwrite. */
  function start(index: number): boolean {
    const box = composer();
    const question = chat.messages.value[index]?.content;
    if (!box || !question || !box.isEmpty()) return false;
    box.restore(question);
    pending.value = { chatId: chat.activeId.value, index, length: chat.messages.value.length };
    return true;
  }

  /** Stops retrying and leaves the box alone (it was used for something else). */
  function forget(): void {
    pending.value = null;
  }

  function cancel(): void {
    if (!pending.value) return;
    forget();
    composer()?.clear();
  }

  /** Sends the box's text in place of the retried question. Still pending when it is not taken. */
  async function resend(
    question: string,
    send: (question: string, options: { truncateTo: number }) => Promise<boolean>,
  ): Promise<boolean> {
    const held = pending.value;
    if (!held) return false;
    forget();
    const taken = await send(question, { truncateTo: held.index });
    if (!taken) pending.value = held;
    return taken;
  }

  watch([chat.activeId, () => chat.messages.value.length], ([chatId, length]) => {
    if (pending.value && (pending.value.chatId !== chatId || pending.value.length !== length)) cancel();
  });

  return { active, shown, start, cancel, forget, resend };
}
