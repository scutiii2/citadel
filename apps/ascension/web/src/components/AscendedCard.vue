<script setup lang="ts">
import { computed } from "vue";
import type { OwnedAscended } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { formatCountdown, titleCase } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmBar from "./ui/EmBar.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";

/** One owned Ascended on the Collection tab: its small card (tier colour, level) with a
 * caption of tier, copies and XP; a click or Enter opens its details. A fainted Ascended
 * is greyed out and says when it is ready again. */
const props = defineProps<{ ascended: OwnedAscended; selected?: boolean }>();
const emit = defineEmits<{ open: [] }>();
const store = useAscensionStore();
const now = useNowSeconds();
const info = computed(() => store.catalog?.ascendeds.find((s) => s.id === props.ascended.ascended_id) ?? null);
const faintLeft = computed(() => (props.ascended.faint_until === null ? 0 : Math.max(0, props.ascended.faint_until - now.value)));
</script>

<template>
  <div
    class="ascended-card em-lift"
    :class="{ down: faintLeft > 0, 'is-off': faintLeft > 0, selected }"
    :style="{ '--tier': `var(--em-tier-${ascended.tier_id}, var(--em-tier-common))` }"
    role="button"
    tabindex="0"
    :aria-pressed="selected ?? false"
    :aria-label="`${ascended.name}, ${titleCase(ascended.tier_id)}, level ${ascended.level}`"
    @click="emit('open')"
    @keydown.enter.prevent="emit('open')"
    @keydown.space.prevent="emit('open')"
  >
    <AscendedPreviewCard v-if="info" class="face" :ascended="info" :level="ascended.level" :tier-id="ascended.tier_id" show-level />
    <span v-else class="ascended-name">{{ ascended.name }}</span>
    <span v-if="faintLeft > 0" class="ko-badge" aria-hidden="true"><EmIcon name="clock" :size="12" /> Fainted</span>
    <span class="caption">
      <strong class="caption-name">{{ ascended.name }}</strong>
      <span class="star-count em-num" :aria-label="`${ascended.stars} stars`">★ {{ ascended.stars }}</span>
      <span class="tier-line">
        <EmTierBadge :tier-id="ascended.tier_id" />
        <span class="copies em-num">{{ ascended.copies }} {{ ascended.copies === 1 ? "copy" : "copies" }}</span>
      </span>
      <span v-if="faintLeft > 0" class="fainted">
        <EmIcon name="clock" /> Fainted, ready in <strong class="em-num">{{ formatCountdown(faintLeft) }}</strong>
      </span>
      <template v-else-if="ascended.xp_needed !== null">
        <EmBar :value="ascended.xp" :max="ascended.xp_needed" :label="`${ascended.name} XP`" />
        <span class="xp em-num">{{ ascended.xp }} / {{ ascended.xp_needed }} XP</span>
      </template>
      <span v-else class="xp">Highest level reached</span>
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
  padding: 6px;
  border: 1px solid var(--em-border);
  background: linear-gradient(135deg, var(--em-panel), var(--em-bg));
  border-radius: var(--em-radius);
  color: var(--em-text);
  cursor: pointer;
}
.ascended-card.selected { border-color: var(--em-accent); box-shadow: 0 0 0 2px var(--em-accent); }
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
.ko-badge { position: absolute; top: 12px; left: 12px; z-index: 1; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border: 1px solid var(--em-danger); background: var(--em-danger-surface); color: var(--em-danger); font-size: 11px; font-weight: 700; pointer-events: none; }
.star-count { color: var(--em-accent); font-size: 12px; }
.caption {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.caption-name { font-size: 13px; line-height: 1.4; overflow-wrap: anywhere; }
.tier-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
}
.copies,
.xp {
  font-size: 12px;
  color: var(--em-muted);
}
.fainted {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--em-danger);
}
</style>
