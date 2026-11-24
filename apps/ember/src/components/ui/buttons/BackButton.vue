<script setup lang="ts">
/** "‹ All notes": the way back from a detail pane to its list. Shown only below
 * 768px, where the list and the detail take turns; on a wider screen both are
 * visible and it is hidden. The label goes in the slot; `@click`, `disabled`
 * pass through. It is a `.chip` (styled by infoPage.css on info pages). */
</script>

<template>
  <button type="button" class="back-button chip">‹ <slot /></button>
</template>

<style scoped>
.back-button { display: none; }
@media (max-width: 767px) {
  .back-button { display: inline-block; min-height: 44px; }
}
</style>
