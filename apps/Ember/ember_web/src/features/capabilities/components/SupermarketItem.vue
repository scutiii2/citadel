<script setup lang="ts">
import CapabilityHeading from "./CapabilityHeading.vue";

/** One row of the Supermarket: a built-in capability or an extension, what it
 * brings, and whether it is added to the account. The parent decides what Add
 * and Disable mean; extra actions (an admin's Remove) go in the `actions` slot. */
withDefaults(
  defineProps<{
    label: string;
    name: string;
    icon: "builtin" | "extension";
    summary: string;
    added: boolean;
    /** Off for everyone (an administrator turned it off): it cannot be added. */
    locked?: boolean;
    /** The summary is a problem (an extension that is not connected). */
    failed?: boolean;
    /** The add button's text and what "added" says; a private extension is "Enable" / "Enabled". */
    addLabel?: string;
    addedLabel?: string;
    /** A muted line under the name (why an extension cannot be reached). */
    detail?: string;
  }>(),
  { addLabel: "Add", addedLabel: "Added", detail: "" },
);
const emit = defineEmits<{ add: []; disable: [] }>();
</script>

<template>
  <article :class="['item', { off: locked && !added }]">
    <CapabilityHeading :label="label" :name="name" :summary="summary" :icon="icon" :problem="failed" :detail="detail" />
    <span class="actions">
      <slot name="actions" />
      <template v-if="added">
        <span class="added">
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 8.5l3.2 3L13 4.5" /></svg>
          {{ addedLabel }}
        </span>
        <button type="button" class="secondary" :aria-label="`Disable ${label}`" @click="emit('disable')">Disable</button>
      </template>
      <span v-else-if="locked" class="status-badge">Off for everyone</span>
      <button v-else type="button" class="add" :aria-label="`${addLabel} ${label}`" @click="emit('add')">{{ addLabel }}</button>
    </span>
  </article>
</template>

<style scoped>
.item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  margin-bottom: 8px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.item.off {
  opacity: 0.75;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.added {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.85em;
  color: var(--success);
}
.added svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
button {
  padding: 4px 14px;
  border-radius: var(--radius-full);
  cursor: pointer;
  font-size: 0.85em;
}
button.add {
  border: 1px solid var(--accent);
  font-weight: 600;
  color: var(--accent-contrast);
  background: var(--accent);
}
button.secondary {
  border: 1px solid var(--border);
  color: var(--text);
  background: transparent;
}
button.secondary:hover {
  border-color: var(--accent);
}
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
