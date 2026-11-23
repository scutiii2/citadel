<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import BaseModal from "../BaseModal.vue";
import ConfirmModal from "./ConfirmModal.vue";

const props = defineProps<{
  open: boolean;
  title: string;
  editable?: boolean;
  editing?: boolean;
  busy?: boolean;
  saveLabel?: string;
  fallbackFocus?: () => void;
}>();
const emit = defineEmits<{ edit: []; close: []; discard: []; save: [] }>();
const expanded = ref(false);
const confirmation = ref<"save" | "discard" | "close">();
const editButton = ref<HTMLButtonElement>();
const body = ref<HTMLElement>();
let opener: HTMLElement | undefined;

watch(() => props.open, async (open) => {
  if (open) {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : undefined;
    return;
  }
  expanded.value = false;
  confirmation.value = undefined;
  // Both the record and its confirmation can close in the same Vue update.
  await nextTick();
  await nextTick();
  if (props.open || !body.value?.isConnected) return;
  if (opener?.isConnected && opener !== document.body && opener.getClientRects().length) {
    opener.focus({ preventScroll: true });
  } else if (document.activeElement === document.body) {
    props.fallbackFocus?.();
  }
  opener = undefined;
});

watch(() => props.editing, async (editing) => {
  await nextTick();
  await nextTick();
  if (!props.open) return;
  if (editing) body.value?.querySelector<HTMLElement>("input:not(:disabled), textarea:not(:disabled), select:not(:disabled)")?.focus();
  else editButton.value?.focus();
});

function requestClose(close: boolean) {
  if (props.busy || confirmation.value) return;
  if (props.editing) confirmation.value = close ? "close" : "discard";
  else emit("close");
}

function requestSave() {
  if (!props.busy && !confirmation.value) confirmation.value = "save";
}

function confirm() {
  const action = confirmation.value;
  confirmation.value = undefined;
  if (action === "save") emit("save");
  else if (action === "discard") emit("discard");
  else if (action === "close") emit("close");
}

defineExpose({ requestSave, requestCancel: () => requestClose(false) });
</script>

<template>
  <BaseModal :open="open" :title="title" side class="record-drawer" :class="{ expanded, 'can-edit': editable }" @close="requestClose(true)">
    <div class="drawer-tools">
      <button v-if="editable && !editing" ref="editButton" type="button" class="admin-icon" aria-label="Edit" title="Edit" data-test="edit" @click="emit('edit')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 5 5 5m-15 9 1-5L16 3l5 5L10 19l-6 1z" /></svg>
      </button>
      <button type="button" class="admin-icon" :aria-label="expanded ? 'Restore drawer size' : 'Expand drawer'" :aria-pressed="expanded" @click="expanded = !expanded">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="expanded ? 'M8 3v5H3m13-5v5h5M3 16h5v5m13-5h-5v5' : 'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5'" /></svg>
      </button>
    </div>
    <div ref="body" class="drawer-body"><slot /></div>
    <footer v-if="$slots.footer" class="drawer-footer"><slot name="footer" /></footer>
  </BaseModal>
  <ConfirmModal
    :open="!!confirmation"
    :title="confirmation === 'save' ? 'Save changes?' : 'Discard changes?'"
    :message="confirmation === 'save' ? 'Apply these changes?' : 'Your changes will be lost.'"
    :confirm-label="confirmation === 'save' ? saveLabel || 'Save changes' : 'Discard changes'"
    @confirm="confirm"
    @close="confirmation = undefined"
  />
</template>

<style scoped>
dialog.record-drawer.side-modal:modal { display: flex; flex-direction: column; inset: 0 0 0 auto; width: min(520px, 100vw); height: 100dvh; max-height: 100dvh; padding: 0; border-radius: 0; overflow: hidden; }
dialog.record-drawer.expanded:modal { width: 90vw; }
.record-drawer > :deep(header) { min-height: 68px; margin: 0; padding: 12px 16px 12px 24px; }
.record-drawer > :deep(header h3) { min-width: 0; padding-inline-end: 46px; overflow-wrap: anywhere; }
.can-edit > :deep(header h3) { padding-inline-end: 90px; }
.record-drawer > :deep(header .close) { flex: none; width: 44px; height: 44px; padding: 0; border-radius: var(--radius-md); }
.record-drawer > :deep(header .close:hover) { background: var(--surface); color: var(--text); }
.drawer-tools { position: absolute; inset: 12px 60px auto auto; display: flex; }
.drawer-tools .admin-icon { width: 44px; height: 44px; }
.drawer-body { flex: 1; min-height: 0; overflow: auto; scrollbar-gutter: stable; overscroll-behavior: contain; padding: 0 24px 24px; }
.drawer-footer { display: flex; flex-shrink: 0; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--border); padding: 12px 24px calc(12px + env(safe-area-inset-bottom, 0px)); }
@media (max-width: 767px) {
  dialog.record-drawer.expanded:modal { width: 100vw; max-width: 100vw; }
  .record-drawer > :deep(header) { padding-inline: 16px 8px; }
  .drawer-tools { inset-inline-end: 52px; }
  .drawer-body, .drawer-footer { padding-inline: 16px; }
}
</style>
