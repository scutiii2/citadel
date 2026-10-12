<script setup lang="ts">
import { computed } from "vue";

/** A tier's EMBLEM drawn from its art (assets/emblems/emblem_<tier>.webp). Decorative: the
 * tier name is always written beside it. An unknown tier shows the common EMBLEM. */
const props = withDefaults(defineProps<{ tierId: string; size?: number }>(), { size: 32 });
const EMBLEMS = import.meta.glob<string>("../../assets/emblems/*.webp", { eager: true, import: "default" });
const url = computed(() => EMBLEMS[`../../assets/emblems/emblem_${props.tierId}.webp`] ?? EMBLEMS["../../assets/emblems/emblem_common.webp"]!);
</script>

<template>
  <img class="em-emblem" :src="url" :width="size" :height="size" alt="" draggable="false" />
</template>

<style scoped>
.em-emblem {
  flex: none;
  display: inline-block;
  object-fit: contain;
  image-rendering: pixelated;
  user-select: none;
}
</style>
