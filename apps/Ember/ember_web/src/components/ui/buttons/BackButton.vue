<script setup lang="ts">
/** "‹ All notes": the way back from a detail pane to its list. Shown only below
 * 768px, where the list and the detail take turns; on a wider screen both are
 * visible and it is hidden. The label goes in the slot; `@click`, `disabled`
 * pass through. `ghost` is a plain text link look; the default is a `.chip`
 * (styled by infoPage.css on info pages). */
defineProps<{ ghost?: boolean }>();
</script>

<template>
  <button type="button" class="back-button" :class="ghost ? 'ghost' : 'chip'">‹ <slot /></button>
</template>

<style scoped>
.back-button { display: none; }
@media (max-width: 767px) {
  .back-button { display: inline-block; min-height: 44px; }
  .back-button.ghost { padding: 6px 0; border: 0; color: var(--muted); font-size: 1.1em; }
}
</style>
