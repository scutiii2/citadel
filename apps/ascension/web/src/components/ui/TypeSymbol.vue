<script setup lang="ts">
import { computed } from "vue";
import { FLAT_BELOW, typeLabel, typeSymbolUrl } from "../../utils/ascensionTypes";

/** An Ascension Type's symbol. `size` is its edge in px, or any CSS length (such as a
 * `cqw` size that scales with a card); the flat symbol is used under FLAT_BELOW px and
 * when `flat` is set. It renders nothing for a type without a symbol, so callers keep
 * the type's name beside it. `decorative` hides it from screen readers when the name is
 * already written next to it. */
const props = withDefaults(defineProps<{ typeId: string; size?: number | string; flat?: boolean; decorative?: boolean }>(), {
  size: 24,
  flat: undefined,
  decorative: false,
});

const flatForSize = computed(() => props.flat ?? (typeof props.size === "number" && props.size < FLAT_BELOW));
const url = computed(() => typeSymbolUrl(props.typeId, flatForSize.value));
const edge = computed(() => (typeof props.size === "number" ? `${props.size}px` : props.size));
const label = computed(() => `${typeLabel(props.typeId)} type`);
</script>

<template>
  <img
    v-if="url"
    class="type-symbol"
    :src="url"
    :alt="decorative ? '' : label"
    :title="decorative ? undefined : label"
    :style="{ width: edge, height: edge }"
    draggable="false"
  />
</template>

<style scoped>
.type-symbol {
  flex: none;
  display: inline-block;
  object-fit: contain;
  vertical-align: middle;
  user-select: none;
}
</style>
