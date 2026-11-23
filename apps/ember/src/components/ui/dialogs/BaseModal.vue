<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

/** A modal dialog the parent opens and closes with `open`. It closes itself on
 * Escape, on the × and on a click outside the panel, by asking the parent
 * (`close`) rather than hiding on its own. The default slot is the body. */
const props = defineProps<{ open: boolean; title: string; wide?: boolean; side?: boolean }>();
const emit = defineEmits<{ close: [] }>();

const dialog = ref<HTMLDialogElement | null>(null);
let unmounting = false;

onBeforeUnmount(() => {
  unmounting = true;
  // A conditional parent can remove the dialog before the open watcher runs.
  // Close it while connected so the browser can return focus to the opener.
  if (dialog.value?.open) dialog.value.close?.();
});

watch(
  () => props.open,
  async (isOpen) => {
    await nextTick();
    if (isOpen && !dialog.value?.open) dialog.value?.showModal();
    else if (!isOpen && dialog.value?.open) dialog.value.close();
  },
  { immediate: true },
);

/** The browser fires `close` for a close made from code too. When the parent
 * already set `open` to false it asked for that, so it must not hear it back:
 * it may be switching to another dialog, and the echo would shut that one. */
function onNativeClose(): void {
  if (props.open && !unmounting) emit("close");
}

/** A click on the backdrop lands on the <dialog> itself, not on its content. */
function onClick(event: MouseEvent): void {
  if (event.target === dialog.value) emit("close");
}
</script>

<template>
  <dialog ref="dialog" class="modal" :class="{ wide, 'side-modal': side }" :aria-label="title" @close="onNativeClose" @cancel.prevent="emit('close')" @click="onClick">
    <header>
      <h3>{{ title }}</h3>
      <button type="button" class="close" aria-label="Close" @click="emit('close')">×</button>
    </header>
    <slot />
  </dialog>
</template>

<style scoped>
.modal {
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100dvh - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px) - 64px);
  padding: 18px 20px 20px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  color: var(--text);
  background: var(--surface);
}
.modal.wide {
  width: min(1000px, calc(100vw - 32px));
}
.modal::backdrop {
  background: rgb(0 0 0 / 45%);
}
dialog.modal.side-modal {
  position: fixed;
  inset: 0 0 0 auto;
  margin: 0;
  width: min(440px, 100vw);
  height: 100dvh;
  max-height: 100dvh;
  padding: 24px;
  border-radius: 0;
  background: var(--bg);
}
@media (max-width: 767px) {
  dialog.modal.side-modal {
    inset: auto 0 var(--rail-height) 0;
    width: 100%;
    height: auto;
    max-height: calc(100dvh - var(--rail-height) - 24px);
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
h3 {
  margin: 0;
  font-size: 1em;
}
.close {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 1.4em;
  line-height: 1;
  color: var(--muted);
}
@media (pointer: coarse), (max-width: 767px) {
  button.close { min-width: 44px; min-height: 44px; }
}
</style>
