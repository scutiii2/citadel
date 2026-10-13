<script setup lang="ts">
import EmIcon from "./EmIcon.vue";
import type { IconName } from "./icons";

/** A full-width menu row: icon, label and an arrow. `primary` is the copper one (one
 * per menu), `danger` the red one for a destructive action. */
withDefaults(defineProps<{ icon: IconName; variant?: "primary" | "secondary" | "danger"; disabled?: boolean; showArrow?: boolean }>(), {
  variant: "secondary",
  disabled: false,
  showArrow: true,
});
</script>

<template>
  <button type="button" class="em-row" :class="variant" :disabled="disabled">
    <slot name="icon"><EmIcon :name="icon" :size="20" /></slot>
    <span class="label"><slot /></span>
    <slot name="trailing"><EmIcon v-if="showArrow" name="arrow" class="arrow" /></slot>
  </button>
</template>

<style scoped>
.em-row {
  display: flex;
  align-items: center;
  gap: var(--em-space-3);
  width: 100%;
  min-height: var(--em-target);
  padding: 10px 18px;
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  color: var(--em-text);
  background: linear-gradient(180deg,#163044,#0c1e2d);
  box-shadow: inset 0 0 0 2px #071623, inset 0 3px 0 #66839744, 0 3px 0 #040d16;
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  transition: filter 120ms ease;
}
.em-row:hover:not(:disabled) {
  filter: brightness(1.12);
}
.label {
  flex: 1;
}
.arrow {
  margin-left: auto;
}
.primary {
  border-color: var(--em-accent);
  color: var(--em-on-accent);
  background: linear-gradient(180deg,#facd8c,#e79751);
  outline: 1px solid #9c6338;
  outline-offset: 2px;
  box-shadow: 0 3px 0 var(--em-accent-edge);
}
.primary:hover:not(:disabled) {
  filter: brightness(1.12);
}
.danger {
  border-color: var(--em-danger);
  color: var(--em-danger);
  background: var(--em-danger-surface);
}
.em-row:disabled {
  border-color: var(--em-disabled-border);
  color: var(--em-disabled-text);
  background: var(--em-disabled-surface);
  box-shadow: none;
  cursor: default;
}
</style>
