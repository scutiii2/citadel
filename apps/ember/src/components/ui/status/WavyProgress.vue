<script setup lang="ts">
import { computed } from "vue";

/** A determinate progress bar whose finished part is a moving wave and whose remaining part is a flat track
 * ending in a dot. For long-running jobs (a download, a merge); everything else uses a flat bar.
 * `value` is 0 to 100 and is the one source for the width and the semantics. `null` means progress is not
 * known yet: the wave then runs the whole width and the bar reports no value. */
const props = defineProps<{ label: string; value: number | null }>();
const known = computed(() => props.value !== null);
const fraction = computed(() => (props.value === null ? 1 : Math.min(1, Math.max(0, props.value / 100))));
</script>

<template>
  <div
    class="wavy-progress" :class="{ empty: fraction === 0, full: fraction === 1 }" :style="{ '--p': fraction }"
    role="progressbar" :aria-label="label" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="known ? Math.round(fraction * 100) : undefined"
  >
    <span class="wave" aria-hidden="true" />
    <span class="rest" aria-hidden="true"><i class="dot" /></span>
  </div>
</template>

<style scoped>
.wavy-progress {
  --gap: 4px;
  --wave: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='10' viewBox='0 0 20 10'%3E%3Cpath d='M0 5Q5 0 10 5T20 5' fill='none' stroke='black' stroke-width='3' stroke-linecap='round'/%3E%3C/svg%3E");
  display: flex;
  align-items: center;
  gap: var(--gap);
  width: 100%;
  height: 10px;
}
/* Nothing finished, or everything finished: there is no neighbour to leave a gap for. */
.empty, .full { gap: 0; }
.wave {
  flex: none;
  width: calc((100% - var(--gap)) * var(--p));
  height: 100%;
  background: var(--accent);
  mask: var(--wave) 0 0 / 20px 100% repeat-x;
  animation: wavy-slide 0.8s linear infinite;
}
.empty .wave { display: none; }
.full .wave { width: 100%; }
.rest {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 4px;
  border-radius: var(--radius-full);
  background: var(--border);
}
.full .rest { display: none; }
.dot {
  position: absolute;
  top: 50%;
  right: 3px;
  width: 4px;
  height: 4px;
  translate: 0 -50%;
  border-radius: var(--radius-full);
  background: var(--accent);
}
/* Without mask support the finished part is a flat fill. */
@supports not (mask: url("x.svg")) {
  .wave { height: 4px; border-radius: var(--radius-full); animation: none; }
}
@keyframes wavy-slide { to { mask-position: 20px 0; } }
</style>
