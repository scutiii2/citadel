<script setup lang="ts">
import { useId } from "vue";

/** The bordered card with a heading that wraps a calendar settings panel; the default slot is its body. */
defineProps<{ title: string }>();
const titleId = useId();
</script>

<template>
  <section class="panel" :aria-labelledby="titleId">
    <h3 :id="titleId">{{ title }}</h3>
    <slot />
  </section>
</template>

<style scoped>
.panel { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
h3 { margin: 0; font-size: 1rem; }
/* The buttons of the panels in the slot. */
.panel :deep(.primary) { min-height: 40px; color: var(--accent-contrast); background: var(--accent); border: 0; border-radius: var(--radius-md); font: inherit; font-weight: 600; cursor: pointer; }
.panel :deep(.chip) { min-height: 32px; padding: 0 10px; color: var(--text); background: transparent; border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; cursor: pointer; }
</style>
