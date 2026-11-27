<script setup lang="ts">
import { computed } from "vue";

/** A small ring filled to `percent`, with a diamond in the middle. Decorative: the control that holds it says the
 * number in words. `danger` turns the fill to the danger colour. */
const props = defineProps<{ percent: number; danger?: boolean }>();
const share = computed(() => Math.min(100, Math.max(0, props.percent)));
</script>

<template>
  <svg class="ring" :class="{ danger }" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
    <circle class="track" cx="12" cy="12" r="9" />
    <!-- Starts at the top and runs clockwise; pathLength makes the dash a percentage. -->
    <circle v-if="share > 0" class="arc" cx="12" cy="12" r="9" pathLength="100" :stroke-dasharray="`${share} 100`" transform="rotate(-90 12 12)" />
    <path class="core" d="M12 8.6 15.4 12 12 15.4 8.6 12z" />
  </svg>
</template>

<style scoped>
.ring {
  display: block;
}
.track,
.arc {
  fill: none;
  stroke-width: 2.6;
}
.track {
  stroke: var(--border);
}
.arc {
  stroke: var(--accent);
  stroke-linecap: round;
}
.ring.danger .arc {
  stroke: var(--danger);
}
.core {
  fill: var(--muted);
}
.ring.danger .core {
  fill: var(--danger);
}
</style>
