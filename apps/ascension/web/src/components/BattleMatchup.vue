<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo, EncounterPreview, OwnedAscended } from "../api/AscensionClient";
import { ascendedStats } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmIcon from "./ui/EmIcon.vue";

/** The two fighters of a battle about to start, each as the preview card (tier colour, level,
 * stats): the wild opponent on the left, your chosen fighter on the right. */
const props = withDefaults(defineProps<{
  player: OwnedAscended | null;
  playerInfo: AscendedInfo | null;
  wild: EncounterPreview | null;
  wildInfo: AscendedInfo | null;
  playerMultiplier: number;
  wildMultiplier?: number;
}>(), { wildMultiplier: 1 });

const player = computed(() => (props.player && props.playerInfo ? {
  info: props.playerInfo,
  level: props.player.level,
  tierId: props.player.tier_id,
  stars: props.player.stars,
  stats: ascendedStats(props.playerInfo, props.player.level, props.playerMultiplier),
} : null));
const wild = computed(() => (props.wild && props.wildInfo ? {
  info: props.wildInfo,
  level: props.wild.level,
  tierId: props.wild.tier_id,
  stats: ascendedStats(props.wildInfo, props.wild.level, props.wildMultiplier),
} : null));
</script>

<template>
  <section class="matchup" aria-label="Battle matchup">
    <div class="fighter wild">
      <p class="fighter-tag em-eyebrow">Wild opponent</p>
      <AscendedPreviewCard v-if="wild" class="face" :ascended="wild.info" :level="wild.level" :tier-id="wild.tierId" :stats="wild.stats" show-level />
    </div>
    <div class="fighter player">
      <p class="fighter-tag em-eyebrow">Your fighter</p>
      <AscendedPreviewCard v-if="player" class="face" :ascended="player.info" :level="player.level" :tier-id="player.tierId" :stars="player.stars" :stats="player.stats" show-level />
      <div v-else class="no-fighter">Choose a fighter</div>
    </div>
    <p class="hidden-personalities"><EmIcon name="book" :size="14" /> Opponent personalities stay hidden until capture</p>
  </section>
</template>

<style scoped>
.matchup {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--em-space-4);
  padding: var(--em-space-4);
  border: 1px solid var(--em-divider);
  border-radius: var(--em-radius);
  background: linear-gradient(150deg, var(--em-header), var(--em-bg));
}
.fighter { display: flex; flex-direction: column; align-items: center; gap: var(--em-space-2); min-width: 0; }
.fighter-tag { margin: 0; }
.wild .fighter-tag { color: var(--em-muted); }
.face { --card-width: min(150px, 100%); }
.no-fighter {
  display: grid;
  place-items: center;
  width: min(150px, 100%);
  aspect-ratio: 265 / 371;
  border: 1px dashed var(--em-divider);
  color: var(--em-muted);
  font-size: 11px;
  text-align: center;
}
.hidden-personalities { grid-column: 1 / -1; display: flex; align-items: center; gap: var(--em-space-2); margin: 0; font-size: 11px; line-height: 1.5; color: var(--em-muted); }
@media (max-width: 700px) {
  .hidden-personalities { font-size: 10px; }
}
</style>
