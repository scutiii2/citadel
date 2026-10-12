<script setup lang="ts">
import { computed } from "vue";
import type { AnimationInfo, AnimationState } from "../../api/AscensionClient";

/** One frame of an animation sheet, played by stepping the background across the grid in CSS (no timers).
 * A state the sheet lacks plays idle. The frame is square and fills the height of its box. */
const props = defineProps<{ sheet: AnimationInfo; state: AnimationState }>();

const clip = computed(() => props.sheet.states[props.state] ?? props.sheet.states.idle!);
const style = computed(() => {
  const { columns, rows } = props.sheet;
  const { row, frames, frame_ms: frameMs, loop } = clip.value;
  return {
    backgroundImage: `url(${props.sheet.url})`,
    backgroundSize: `${columns * 100}% ${rows * 100}%`,
    backgroundPositionY: rows > 1 ? `${(row / (rows - 1)) * 100}%` : "0%",
    "--x-end": columns > 1 ? `${((frames - 1) / (columns - 1)) * 100}%` : "0%",
    "--frames": frames,
    "--duration": `${frames * frameMs}ms`,
    "--repeat": loop ? "infinite" : "1",
  };
});
</script>

<template>
  <!-- Keyed by state so a new state restarts from its first frame. -->
  <div :key="state" class="animated-sprite" :style="style" role="img" aria-hidden="true" />
</template>

<style scoped>
.animated-sprite {
  height: 100%;
  max-width: 100%;
  aspect-ratio: 1;
  background-repeat: no-repeat;
  animation: sheet-frames var(--duration) steps(var(--frames), jump-none) var(--repeat) forwards;
}
@keyframes sheet-frames {
  from {
    background-position-x: 0%;
  }
  to {
    background-position-x: var(--x-end);
  }
}
</style>
