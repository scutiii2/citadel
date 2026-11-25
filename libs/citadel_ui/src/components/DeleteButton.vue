<script setup lang="ts">
/** A destructive action button. While `busy` (the request is in flight) the label and the bin fade out
 * and a small spinner fades in at the centre. The button never changes size: the label stays in the
 * layout, only invisible, so the busy state cannot make the row or dialog jump. The animation only
 * follows `busy`, so it never delays or replaces the action itself. A click while busy is ignored. */
const props = withDefaults(defineProps<{ label?: string; busy?: boolean; disabled?: boolean }>(), {
  label: "Delete",
  busy: false,
  disabled: false,
});
const emit = defineEmits<{ click: [] }>();

function onClick(): void {
  if (props.busy || props.disabled) return;
  emit("click");
}
</script>

<template>
  <button
    type="button"
    class="delete-button"
    :aria-label="label"
    :aria-busy="busy"
    :aria-disabled="disabled || busy"
    :disabled="disabled && !busy"
    @click="onClick"
  >
    <svg class="bin" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
      <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M10 11v6M14 11v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    <span class="label" aria-hidden="true">{{ label }}</span>
    <svg class="ring" viewBox="0 0 40 40" aria-hidden="true">
      <circle cx="20" cy="20" r="17" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-dasharray="26 82" />
    </svg>
  </button>
</template>

<style scoped>
/* button.delete-button, not .delete-button: keeps the bin's left padding against page rules. */
button.delete-button {
  position: relative;
  box-sizing: border-box;
  height: 34px;
  padding: 0 16px 0 38px;
  overflow: hidden;
  border: 1px solid var(--danger);
  border-radius: var(--radius-full);
  cursor: pointer;
  font: inherit;
  font-weight: 600;
  white-space: nowrap;
  color: var(--danger);
  background: transparent;
}
button.delete-button:disabled {
  cursor: default;
  opacity: 0.5;
}
.delete-button[aria-busy="true"] {
  cursor: default;
}
/* The global busy spinner (style.css) would add a second spinner and 18 px of width: this button has its own. */
button.delete-button[aria-busy="true"]::before {
  content: none;
}
.bin {
  position: absolute;
  top: 8px;
  left: 14px;
  transition: opacity 0.15s ease;
}
.label {
  transition: opacity 0.15s ease;
}
/* The spinner sits dead centre and replaces the bin and the label; nothing else changes. */
.ring {
  position: absolute;
  top: calc(50% - 9px);
  left: calc(50% - 9px);
  width: 18px;
  height: 18px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}
.delete-button[aria-busy="true"] .bin,
.delete-button[aria-busy="true"] .label {
  opacity: 0;
}
.delete-button[aria-busy="true"] .ring {
  opacity: 1;
  animation: ring-spin 0.9s linear infinite;
}
@keyframes ring-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
