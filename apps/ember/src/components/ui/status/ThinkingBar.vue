<script setup lang="ts">
/** A thin moving gradient that says "still working" beside a pending answer or task. Purely decorative:
 * pair it with a `role="status"` line that says what is happening. Show it only while the wait lasts, and
 * give it room so its appearing never moves the content around it. */
</script>

<template>
  <span class="thinking-bar" aria-hidden="true" />
</template>

<style scoped>
.thinking-bar {
  display: block;
  width: min(100%, 240px);
  height: 4px;
  margin-top: 8px;
  border-radius: var(--radius-sm);
  /* Same colour at both ends, so adjacent tiles meet without a seam. */
  background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 25%, var(--bg)), var(--accent)) 0 0 / 300% 100% repeat-x;
  mask-image: linear-gradient(90deg, transparent, #000 15%, #000 85%, transparent);
  animation: thinking-slide 2s linear infinite;
}
@keyframes thinking-slide { to { background-position: -300% 0; } }
</style>
