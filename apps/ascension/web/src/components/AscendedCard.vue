<script setup lang="ts">
import { computed } from "vue";
import type { OwnedAscended } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { ascendedStats, formatCountdown, titleCase } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmIcon from "./ui/EmIcon.vue";

/** One owned Ascended on the Collection tab: its small card (tier colour, stars, level) with a
 * caption of its name; a click or Enter opens its details. A fainted Ascended
 * is greyed out and says when it is ready again. */
const props = defineProps<{ ascended: OwnedAscended; selected?: boolean }>();
const emit = defineEmits<{ open: [] }>();
const store = useAscensionStore();
const now = useNowSeconds();
const info = computed(() => store.catalog?.ascendeds.find((s) => s.id === props.ascended.ascended_id) ?? null);
const stats = computed(() => info.value ? ascendedStats(info.value, props.ascended.level, store.catalog?.tiers.find((t) => t.id === props.ascended.tier_id)?.stat_multiplier ?? 1) : undefined);
const faintLeft = computed(() => (props.ascended.faint_until === null ? 0 : Math.max(0, props.ascended.faint_until - now.value)));
</script>

<template>
  <div
    class="ascended-card"
    :class="{ down: faintLeft > 0 }"
    :style="{ '--tier': `var(--em-tier-${ascended.tier_id}, var(--em-tier-common))` }"
    role="button"
    tabindex="0"
    :aria-pressed="selected ?? false"
    :aria-label="`${ascended.name}, ${titleCase(ascended.tier_id)}, level ${ascended.level}`"
    @click="emit('open')"
    @keydown.enter.prevent="emit('open')"
    @keydown.space.prevent="emit('open')"
  >
    <AscendedPreviewCard v-if="info" class="face" :class="{ 'preview-lift': faintLeft === 0 }" :ascended="info" :level="ascended.level" :tier-id="ascended.tier_id" :stars="ascended.stars" :stats="stats" show-level />
    <span v-else class="ascended-name">{{ ascended.name }}</span>
    <span v-if="faintLeft > 0" class="ko-badge" aria-hidden="true"><EmIcon name="clock" :size="12" /> Fainted</span>
    <span class="caption">
      <span v-if="faintLeft > 0" class="fainted">
        <EmIcon name="clock" /> Fainted, ready in <strong class="em-num">{{ formatCountdown(faintLeft) }}</strong>
      </span>
    </span>
  </div>
</template>

<style scoped>
.ascended-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--em-space-2);
  box-sizing: border-box;
  width: var(--card-width, 100%);
  color: var(--em-text);
  cursor: pointer;
}
.ascended-card:focus-visible {
  outline: 2px solid var(--em-accent);
  outline-offset: 3px;
}
.face {
  --card-width: 100%;
}
.ascended-card.down .face {
  filter: grayscale(1);
  opacity: 0.72;
}
.ko-badge { position: absolute; top: 8px; left: 8px; z-index: 1; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border: 1px solid var(--em-danger); background: var(--em-danger-surface); color: var(--em-danger); font-size: 11px; font-weight: 700; pointer-events: none; }
.caption {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fainted {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--em-danger);
}
</style>
