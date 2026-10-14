<script setup lang="ts">
import { computed } from "vue";

/** Decorative Ascended tier art. Callers keep a visible tier name beside it. */
const props = withDefaults(defineProps<{ tierId: string; size?: number }>(), { size: 24 });
const TIERS = import.meta.glob<string>("../../../../design_references/tiers/tier_*.webp", { eager: true, import: "default" });
const url = computed(() => TIERS[`../../../../design_references/tiers/tier_${props.tierId}.webp`]);
</script>

<template>
  <img v-if="url" class="em-tier-icon" :src="url" :width="size" :height="size" alt="" aria-hidden="true" draggable="false" />
</template>

<style scoped>
.em-tier-icon {
  flex: none;
  display: inline-block;
  object-fit: contain;
  image-rendering: pixelated;
  vertical-align: middle;
  user-select: none;
}
</style>
