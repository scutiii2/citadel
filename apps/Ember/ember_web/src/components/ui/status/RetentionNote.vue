<script setup lang="ts">
/** A small clock-icon note that stored files expire, e.g. "Files are kept for 6
 * hours." The text goes in the slot. Spacing is the page's. */
</script>

<template>
  <p class="retention">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6l4 2" /></svg>
    <span><slot /></span>
  </p>
</template>

<style scoped>
.retention { display: flex; align-items: flex-start; gap: 8px; margin: 0; color: var(--muted); font-size: .75em; }
.retention svg { width: 15px; height: 15px; margin-top: 2px; flex-shrink: 0; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
</style>
