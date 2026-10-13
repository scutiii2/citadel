<script setup lang="ts">
import { computed, ref } from "vue";
import type { AscendedInfo, EncounterPreview, OwnedAscended } from "../api/AscensionClient";
import { typeLabel } from "../utils/ascensionTypes";
import { spriteFor } from "../utils/sprites";
import EmIcon from "./ui/EmIcon.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";

const props = defineProps<{
  player: OwnedAscended | null;
  playerInfo: AscendedInfo | null;
  wild: EncounterPreview | null;
  wildInfo: AscendedInfo | null;
  playerMultiplier: number;
}>();
const failedImages = ref<string[]>([]);
const fighters = computed(() => [
  { side: "player", label: "Your fighter", record: props.player, info: props.playerInfo },
  { side: "wild", label: "Wild opponent", record: props.wild, info: props.wildInfo },
].map(fighter => {
  const url = spriteFor(fighter.info?.art, "battle");
  return {
    ...fighter,
    name: fighter.record?.name ?? "Choose a fighter",
    image: url && !failedImages.value.includes(url) ? url : null,
    focus: 50,
    types: (fighter.info?.ascension_types ?? []).map(typeLabel).join(" · "),
  };
}));
const stats = computed(() => {
  if (!props.player || !props.playerInfo) return [];
  const { level } = props.player;
  const { base, growth } = props.playerInfo;
  return [
    { key: "hp", label: "HP" },
    { key: "power", label: "Power" },
    { key: "speed", label: "Speed" },
  ].map(stat => ({
    ...stat,
    value: Math.max(1, Math.floor(((base[stat.key] ?? 0) + (growth[stat.key] ?? 0) * (level - 1)) * props.playerMultiplier + 1e-9)),
  }));
});
</script>

<template>
  <section class="matchup" aria-label="Battle matchup">
    <div v-for="fighter in fighters" :key="fighter.side" class="fighter" :class="fighter.side">
      <img
        v-if="fighter.image"
        :src="fighter.image"
        :style="{ objectPosition: `50% ${fighter.focus}%` }"
        alt=""
        draggable="false"
        @error="failedImages.push(fighter.image)"
      />
      <div v-else class="art-placeholder" aria-hidden="true">
        <span class="letter em-pixel">{{ fighter.record ? fighter.name.slice(0, 1) : '?' }}</span>
      </div>
      <p class="fighter-tag em-eyebrow">{{ fighter.label }}</p>
      <div class="fighter-info">
        <h3 class="ascended-name em-pixel">{{ fighter.name }}</h3>
        <div v-if="fighter.record" class="fighter-meta em-num">
          <span>Level {{ fighter.record.level }}</span>
          <EmTierBadge :tier-id="fighter.record.tier_id" />
          <span v-if="fighter.types" class="types">{{ fighter.types }}</span>
        </div>
      </div>
    </div>
    <span class="versus em-pixel" aria-hidden="true">VS</span>
    <div class="matchup-foot">
      <dl v-if="stats.length" class="stats em-num" aria-label="Selected fighter stats">
        <div v-for="stat in stats" :key="stat.key"><dt>{{ stat.label }}</dt><dd>{{ stat.value }}</dd></div>
      </dl>
      <p class="hidden-personalities"><EmIcon name="book" :size="14" /> Opponent personalities stay hidden until capture</p>
    </div>
  </section>
</template>

<style scoped>
.matchup {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid var(--em-divider);
  border-radius: var(--em-radius);
  background: var(--em-header);
}
.fighter {
  position: relative;
  height: clamp(280px, 29vw, 380px);
  min-width: 0;
  overflow: hidden;
}
.player { border-right: 1px solid var(--em-divider); }
.fighter img, .art-placeholder {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.art-placeholder {
  display: grid;
  place-items: center;
  background: radial-gradient(ellipse at center, var(--em-raised), var(--em-bg));
}
.letter { font-size: 80px; color: var(--em-muted); }
.fighter::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(0deg, var(--em-bg), transparent 58%, color-mix(in srgb, var(--em-bg) 35%, transparent));
  pointer-events: none;
}
.fighter-tag {
  position: absolute;
  z-index: 1;
  top: var(--em-space-5);
  left: var(--em-space-5);
}
.wild .fighter-tag { left: auto; right: var(--em-space-5); color: var(--em-muted); }
.fighter-info {
  position: absolute;
  z-index: 1;
  bottom: var(--em-space-5);
  left: var(--em-space-5);
  right: var(--em-space-5);
}
.ascended-name { margin: 0 0 var(--em-space-2); font-size: 26px; line-height: 1.3; overflow-wrap: anywhere; }
.fighter-meta { display: flex; flex-wrap: wrap; gap: var(--em-space-2); align-items: center; font-size: 12px; color: var(--em-muted); }
.wild .fighter-info { text-align: right; }
.wild .fighter-meta { justify-content: flex-end; }
.versus {
  position: absolute;
  z-index: 2;
  top: calc((100% - 48px) / 2);
  left: 50%;
  transform: translate(-50%, -50%);
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  border: 1px solid var(--em-accent);
  background: var(--em-bg);
  color: var(--em-accent);
  font-size: 22px;
  clip-path: polygon(15% 0, 85% 0, 100% 15%, 100% 85%, 85% 100%, 15% 100%, 0 85%, 0 15%);
}
.matchup-foot {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: var(--em-space-3);
  min-height: 48px;
  padding: var(--em-space-3) var(--em-space-5);
  border-top: 1px solid var(--em-divider);
}
.stats { display: flex; flex-wrap: wrap; gap: var(--em-space-5); margin: 0; }
.stats > div { display: flex; gap: var(--em-space-2); align-items: baseline; }
.stats dt { font-size: 12px; color: var(--em-muted); }
.stats dd { margin: 0; font-size: 14px; font-weight: 700; }
.hidden-personalities { display: flex; align-items: center; gap: var(--em-space-2); font-size: 11px; color: var(--em-muted); }
@media (max-width: 700px) {
  .fighter { height: 250px; }
  .fighter-tag { top: var(--em-space-3); left: var(--em-space-3); font-size: 8px; letter-spacing: 1px; }
  .wild .fighter-tag { right: var(--em-space-3); }
  .fighter-info { bottom: var(--em-space-3); left: var(--em-space-3); right: var(--em-space-3); }
  .ascended-name { font-size: 16px; }
  .fighter-meta { font-size: 10px; gap: var(--em-space-1); }
  .fighter-meta :deep(.em-tier) { font-size: 9px; padding: 1px 4px; gap: var(--em-space-1); }
  .versus { width: 44px; height: 44px; top: 40%; font-size: 14px; }
  .matchup-foot { padding: var(--em-space-3); }
  .stats { gap: var(--em-space-4); }
  .stats dt { font-size: 10px; }
  .stats dd { font-size: 12px; }
  .hidden-personalities { margin-left: auto; font-size: 9px; }
}

.matchup { grid-template-columns: minmax(0, 1fr); background: linear-gradient(150deg, var(--em-header), var(--em-bg)); }
.fighter { height: 220px; }
.wild { order: 0; }
.player { order: 1; height: 150px; border-right: 0; border-top: 1px solid var(--em-divider); }
.fighter img { object-fit: contain; padding: 30px 12px 58px; image-rendering: pixelated; mix-blend-mode: lighten; }
.fighter::after { background: linear-gradient(0deg, var(--em-bg), transparent 36%); }
.fighter-tag, .wild .fighter-tag { top: 10px; left: 10px; right: auto; font-size: 9px; }
.fighter-info, .wild .fighter-info { bottom: 10px; left: 10px; right: 10px; text-align: left; }
.ascended-name { font-size: 15px; margin-bottom: 4px; }
.fighter-meta, .wild .fighter-meta { justify-content: flex-start; font-size: 10px; }
.versus { display: none; }
.matchup-foot { order: 2; padding: 10px; gap: 8px; }
.stats { width: 100%; justify-content: space-between; gap: 6px; }
.hidden-personalities { font-size: 10px; line-height: 1.5; }
@media (max-width: 700px) { .matchup { grid-template-columns: repeat(2, minmax(0, 1fr)); } .wild, .player { height: 210px; order: 0; border-top: 0; } .player { border-right: 1px solid var(--em-divider); } .wild { order: 1; } .matchup-foot { grid-column: 1 / -1; } }

</style>
