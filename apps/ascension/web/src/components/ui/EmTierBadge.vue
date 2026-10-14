<script setup lang="ts">
import { computed } from "vue";
import { titleCase } from "../../utils/ascension";
import EmTierIcon from "./EmTierIcon.vue";

/** A tier's name in its colour, with its artwork. The name is always
 * written (or `label`, for example "Tier 2"), so the colour is never the only signal. */
const props = withDefaults(defineProps<{ tierId: string; label?: string; showIcon?: boolean }>(), { showIcon: true });
const text = computed(() => props.label ?? titleCase(props.tierId));
</script>

<template>
  <span class="em-tier" :style="{ '--tier': `var(--em-tier-${tierId}, var(--em-tier-common))` }"><EmTierIcon v-if="showIcon" :tier-id="tierId" />{{ text }}</span>
</template>

<style scoped>
.em-tier {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--tier);
  border-radius: var(--em-radius);
  color: var(--tier);
  background: var(--em-bg);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
</style>
