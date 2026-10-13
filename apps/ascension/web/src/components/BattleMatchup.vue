<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo, EncounterPreview, Fighter, OwnedAscended } from "../api/AscensionClient";
import { ascendedStats } from "../utils/ascension";
import BattleArena from "./BattleArena.vue";
import EmIcon from "./ui/EmIcon.vue";

/** The preparation screen uses the same stage as battle: your fighter left, opponent right. */
const props = withDefaults(defineProps<{
  player: OwnedAscended | null;
  playerInfo: AscendedInfo | null;
  wild: EncounterPreview | null;
  wildInfo: AscendedInfo | null;
  playerMultiplier: number;
  wildMultiplier?: number;
}>(), { wildMultiplier: 1 });

function previewFighter(info: AscendedInfo | null, level: number, tierId: string, multiplier: number, name: string): Fighter {
  const stats = info ? Object.fromEntries(ascendedStats(info, level, multiplier).map(s => [s.key, s.value])) : {};
  const hp = stats.hp ?? 0;
  return { ascended_id: info?.id ?? "", name: info?.name ?? name, tier_id: tierId, level,
    hp, max_hp: hp, power: stats.power ?? 0, speed: stats.speed ?? 0, buffs: [], defense: null, abilities: [] };
}
const preview = computed(() => ({
  round: 0,
  player: previewFighter(props.player ? props.playerInfo : null, props.player?.level ?? 1, props.player?.tier_id ?? "common", props.playerMultiplier, "Choose a fighter"),
  wild: previewFighter(props.wildInfo, props.wild?.level ?? 1, props.wild?.tier_id ?? "common", props.wildMultiplier, "Wild opponent"),
}));
const infos = computed(() => [props.playerInfo, props.wildInfo].filter((info): info is AscendedInfo => info !== null));
</script>

<template>
  <section class="matchup" aria-label="Battle matchup">
    <BattleArena :battle="preview" :fighter-infos="infos" preview />
    <p class="hidden-personalities"><EmIcon name="book" :size="14" /> Opponent personalities stay hidden until capture</p>
  </section>
</template>

<style scoped>
.matchup { min-width: 0; }
.hidden-personalities { display: flex; align-items: center; gap: var(--em-space-2); margin: 8px 0 0; font-size: 11px; line-height: 1.5; color: var(--em-muted); }
</style>
