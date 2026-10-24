<script setup lang="ts">
/** Bordered, fill-height workspace inside PageLayout wide fill.
 * Set --workspace-columns in the caller's CSS for its desktop/tablet panes.
 * The default slot keeps pane semantics, scroll containers and mobile selection
 * with the feature. No extra wrappers or conditional mounting of pane content.
 */
withDefaults(defineProps<{
  as?: 'div' | 'form';
  /** Single-column framed workspace, or an unframed vertical mobile flow. */
  mobile?: 'single' | 'stack';
}>(), { as: 'div', mobile: 'single' });
</script>

<template>
  <component :is="as" class="workspace-layout" :class="{ 'workspace-layout--stack': mobile === 'stack' }">
    <slot />
  </component>
</template>

<style scoped>
.workspace-layout {
  display: grid;
  grid-template-columns: var(--workspace-columns, minmax(220px, 280px) minmax(0, 1fr));
  flex: 1;
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
@media (max-width: 767px) {
  .workspace-layout { grid-template-columns: minmax(0, 1fr); }
  .workspace-layout--stack {
    display: flex;
    flex-direction: column;
    border: 0;
    border-radius: 0;
  }
}
</style>
