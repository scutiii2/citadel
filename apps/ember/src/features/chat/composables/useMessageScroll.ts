import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";
import type { ChatMessage, ToolStep } from "../../../api/types";

interface MessageScrollState {
  messages: ChatMessage[];
  streaming: string;
  activity: string;
  steps: ToolStep[];
  jumpIndex?: number | null;
}

/** Follow new messages until the reader scrolls up, and reveal search hits. */
export function useMessageScroll(props: MessageScrollState, scroller: Ref<HTMLElement | null>, jumped: () => void) {
  // Within this many px of the bottom counts as "following along".
  const STICK_THRESHOLD_PX = 80;

  // Follow new content only while the user is at the bottom; scrolling up to
  // read something stops it, scrolling back down resumes it.
  const stickToBottom = ref(true);
  // Something arrived while the user was reading further up: shows the
  // "New messages" pill, which brings them back down.
  const hasNew = ref(false);

  function onScroll(): void {
    const el = scroller.value;
    if (!el) return;
    stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD_PX;
    if (stickToBottom.value) hasNew.value = false;
  }

  function jumpToNew(): void {
    const el = scroller.value;
    if (!el) return;
    stickToBottom.value = true;
    hasNew.value = false;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }

  async function scrollToBottomIfSticking(): Promise<void> {
    if (!stickToBottom.value) return;
    await nextTick();
    const el = scroller.value;
    if (el) el.scrollTop = el.scrollHeight;
  }

  watch(
    () => props.messages.length,
    (count, before) => {
      // Sending a question always jumps back to the bottom.
      if (props.messages.at(-1)?.role === "user") stickToBottom.value = true;
      if (!stickToBottom.value && count > before) hasNew.value = true;
      void scrollToBottomIfSticking();
    },
  );
  watch(
    () => [props.streaming, props.activity, props.steps.length],
    () => {
      if (!stickToBottom.value) hasNew.value = true;
      void scrollToBottomIfSticking();
    },
  );

  const FLASH_MS = 1600;
  // The message a search result pointed at, highlighted for a moment.
  const flashIndex = ref<number | null>(null);
  let flashTimer: ReturnType<typeof setTimeout> | null = null;

  // Scrolls to the requested message once it is rendered (immediate: this list
  // only mounts after the chat's transcript has loaded). A target past the end
  // of the chat is dropped.
  watch(
    () => [props.jumpIndex, props.messages.length] as const,
    async ([index, count]) => {
      if (index === null || index === undefined) return;
      if (index >= count) {
        jumped();
        return;
      }
      await nextTick();
      const target = scroller.value?.querySelector<HTMLElement>(`[data-index="${index}"]`);
      if (!target) return;
      stickToBottom.value = false; // reading history: don't follow new content
      target.scrollIntoView({ block: "center" });
      flashIndex.value = index;
      if (flashTimer !== null) clearTimeout(flashTimer);
      flashTimer = setTimeout(() => (flashIndex.value = null), FLASH_MS);
      jumped();
    },
    { immediate: true, flush: "post" },
  );

  // A fresh list starts at the top; land on the latest message unless a search
  // jump is about to scroll somewhere else.
  onMounted(() => {
    if (props.jumpIndex === null || props.jumpIndex === undefined) void scrollToBottomIfSticking();
  });

  onBeforeUnmount(() => {
    if (flashTimer !== null) clearTimeout(flashTimer);
  });

  return { hasNew, stickToBottom, flashIndex, onScroll, jumpToNew };
}
