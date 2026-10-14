<script setup lang="ts">
import { computed } from "vue";

/** Decorative essence art; callers keep the tier label beside it. Vite bundles the
 * original design references so all six tiers share one source of artwork. */
const props = withDefaults(defineProps<{ tierId: string; size?: number }>(), { size: 28 });
const ESSENCES = import.meta.glob<string>("../../../../_others/design_references/essences/*.webp", { eager: true, import: "default" });
const url = computed(() => ESSENCES[`../../../../_others/design_references/essences/essence_${props.tierId}.webp`]);
</script>

<template>
  <img v-if="url" class="em-essence" :src="url" :width="size" :height="size" alt="" draggable="false" />
</template>

<style scoped>
.em-essence {
  flex: none;
  display: inline-block;
  object-fit: contain;
  image-rendering: pixelated;
  vertical-align: middle;
  user-select: none;
}
</style>
