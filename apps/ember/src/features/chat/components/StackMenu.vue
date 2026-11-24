<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, useId, useTemplateRef, watch } from "vue";
import { useOutsideClose } from "../../../composables/useOutsideClose";
import { useAuthStore } from "../../../stores/auth";
import ShareDialog, { type ShareTarget } from "../../sharing/components/ShareDialog.vue";
import { useStackStore } from "../stores/stack";
import StackPanel from "./StackPanel.vue";

/** The Memory control in the chat header: how much short-term memory the chat holds, and the panel to manage it.
 * A non-modal popover (a sheet above the nav bar on a phone): Esc or a press outside closes it. The memory is
 * private to the chat: it is dropped when the chat changes and when this control goes away. */
const props = defineProps<{ chatId: string | null; locked: boolean }>();

const store = useStackStore();
const auth = useAuthStore();
const active = ref(true);
const panelId = useId();
const open = ref(false);
const shareTarget = ref<ShareTarget | null>(null);
const box = useTemplateRef<HTMLElement>("box");
const button = useTemplateRef<HTMLButtonElement>("button");
const panel = useTemplateRef<InstanceType<typeof StackPanel>>("panel");

const shown = computed(() => (active.value && auth.account && props.chatId ? store.entry(props.chatId) : null));
const view = computed(() => shown.value?.view ?? null);
const level = computed(() => (view.value?.full ? "full" : view.value?.warn ? "warn" : ""));
const countText = computed(() => (view.value ? `${view.value.used}/${view.value.limit}` : ""));

function close(): void {
  shareTarget.value = null;
  open.value = false;
}

function closeOnEscape(event: KeyboardEvent): void {
  if (event.key !== "Escape" || event.repeat || shareTarget.value) return;
  close();
  button.value?.focus();
}

function shareItem(itemId: number): void {
  if (!props.chatId || !open.value || shown.value?.pending || shown.value?.compacting) return;
  shareTarget.value = { kind: "stack_item", chatId: props.chatId, itemId, label: "a short-term memory item" };
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener("keydown", closeOnEscape);
    if (props.chatId) void store.load(props.chatId);
  } else {
    document.removeEventListener("keydown", closeOnEscape);
  }
});
useOutsideClose(box, open, close);

watch([() => props.chatId, () => auth.account?.id, active], ([next, accountId, isActive], [previous]) => {
  if (previous) store.forget(previous);
  close();
  if (next && accountId !== undefined && isActive) void store.load(next);
}, { immediate: true });

// ChatView is cached when another page opens. Drop its private panel and document listeners then, too.
onActivated(() => { active.value = true; });
onDeactivated(() => { active.value = false; });

// Agents save to memory while they answer: look again when the answer is done.
watch(() => props.locked, (locked, wasLocked) => {
  if (wasLocked && !locked && active.value && props.chatId) void store.load(props.chatId);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", closeOnEscape);
  if (props.chatId) store.forget(props.chatId);
});

async function add(text: string): Promise<void> {
  const origin = panel.value;
  if (props.chatId && (await store.add(props.chatId, text)) && panel.value === origin) origin?.clearDraft();
}
</script>

<template>
  <div v-if="chatId && shown" ref="box" class="stack-box">
    <button
      ref="button" type="button" class="stack-button" :class="level" data-test="stack-button" aria-haspopup="dialog" :aria-expanded="open" :aria-controls="open ? panelId : undefined"
      title="Short-term memory: the short facts saved for this chat" @click="open ? close() : (open = true)"
    >
      <svg v-if="level" class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
      Memory
      <span v-if="countText" class="count">{{ countText }}</span>
      <span v-if="level === 'full'" class="level">full</span>
      <span v-else-if="level === 'warn'" class="level">nearly full</span>
    </button>
    <StackPanel
      v-if="open"
      ref="panel"
      :id="panelId"
      class="panel"
      :status="shown.status === 'idle' ? 'loading' : shown.status"
      :view="view"
      :error="shown.error"
      :add-error="shown.addError"
      :pending="shown.pending"
      :compacting="shown.compacting"
      :notice="shown.notice"
      :locked="locked"
      @add="add"
      @pin="(id, pinned) => store.setPinned(chatId!, id, pinned)"
      @share="shareItem"
      @remove="(id) => store.remove(chatId!, id)"
      @compact="store.compact(chatId!)"
      @retry="store.load(chatId!)"
    />
    <ShareDialog v-if="shareTarget" :open="true" :target="shareTarget" @close="shareTarget = null" />
  </div>
</template>

<style scoped>
.stack-button {
  display: inline-flex; align-items: center; gap: 6px; padding: 2px 6px; border: none; border-radius: var(--radius-md);
  cursor: pointer; background: transparent; color: var(--muted); font: inherit; font-size: 0.8em;
}
.stack-button:hover, .stack-button[aria-expanded="true"] { background: var(--code-bg); }
.stack-button.warn .line-icon { color: var(--warning); }
.stack-button.full .line-icon { color: var(--danger); }
.count { font-variant-numeric: tabular-nums; }
.panel { position: absolute; top: calc(100% + 6px); right: 16px; z-index: 30; }
@media (min-width: 768px) {
  .panel { max-width: calc(100% - 32px); }
}
@media (max-width: 767px) {
  .stack-button { min-width: 44px; min-height: 44px; justify-content: center; }
  .panel {
    position: fixed; top: auto; right: env(safe-area-inset-right, 0px); left: env(safe-area-inset-left, 0px);
    bottom: calc(var(--rail-height) + 100dvh - var(--app-viewport-height, 100dvh) - var(--app-viewport-top, 0px));
    z-index: 40; width: auto;
    max-height: min(70dvh, calc(var(--app-viewport-height, 100dvh) - var(--rail-height) - env(safe-area-inset-top, 0px)));
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
}
</style>
