<script setup lang="ts">
/** The red-outlined row at the end of an editor or dialog: a short `label`
 * (or the `label` slot, e.g. a bold "Danger zone") and the destructive button
 * in the default slot. The button asks for confirmation; this only lays it out.
 * Spacing around the row is the page's, set with its own class. */
defineProps<{ label?: string }>();
</script>

<template>
  <div class="danger-panel">
    <slot name="label"><span>{{ label }}</span></slot>
    <slot />
  </div>
</template>

<style scoped>
.danger-panel { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-lg); font-size: .85em; }
.danger-panel :deep(button.action) { color: var(--danger); border-color: var(--danger); border-radius: var(--radius-full); }
.danger-panel :deep(.action .label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
.danger-panel :deep(.action .icon) { stroke: currentColor; }
</style>
