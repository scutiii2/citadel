<script setup lang="ts">
import { computed } from "vue";
import type { BattleView, Buff, Fighter } from "../api/AscensionClient";
import { usePlaybackStore } from "../stores/playback";
import { ascendedArt } from "./ascendedArt";
import EmBar from "./ui/EmBar.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";

/** Both Ascended facing each other across a VS marker: name, level, tier, health, their
 * portrait, and what is affecting them (buffs, defense). The numbers are always written. */
const props = defineProps<{ battle: BattleView }>();
const playback = usePlaybackStore();

const sides = computed<{ key: string; label: string; fighter: Fighter }[]>(() => [
  { key: "player", label: "You", fighter: props.battle.player },
  { key: "wild", label: "Wild", fighter: props.battle.wild },
]);

function buffText(buff: Buff): string {
  const lasting =
    buff.rounds_left === null ? " for the whole battle" : `, ${buff.rounds_left} ${buff.rounds_left === 1 ? "round" : "rounds"} left`;
  return `+${buff.amount} ${buff.stat}${lasting}`;
}

function effects(fighter: Fighter): string[] {
  const list = fighter.buffs.map(buffText);
  if (fighter.defense) {
    const d = fighter.defense;
    list.push(`Defense ${d.rating}: ${d.attacks_left} attacks or ${d.rounds_left} rounds left`);
  }
  return list;
}

/** The health to draw: the old value until a playing hit lands. */
function hpOf(key: string, fighter: Fighter): number {
  return playback.hp?.[key as "player" | "wild"] ?? fighter.hp;
}

function art(fighter: Fighter): string | null {
  return ascendedArt(fighter.ascended_id)?.url ?? null;
}
</script>

<template>
  <section class="arena em-glow" :class="{ playing: playback.busy }" :aria-label="`Round ${battle.round}`" @click="playback.busy && playback.skip()">
    <button v-if="playback.busy" type="button" class="skip" @click.stop="playback.skip()">Skip</button>
    <div class="fighters">
      <template v-for="(side, i) in sides" :key="side.key">
        <div v-if="i === 1" class="versus em-pixel" aria-hidden="true">VS</div>
        <article class="fighter" :class="side.key" :aria-label="`${side.label}: ${side.fighter.name}`">
          <div class="head">
            <h3>{{ side.fighter.name }} <small class="em-num">Lv. {{ side.fighter.level }}</small></h3>
            <EmTierBadge :tier-id="side.fighter.tier_id" />
          </div>
          <EmBar kind="hp" :value="hpOf(side.key, side.fighter)" :max="side.fighter.max_hp" :label="`${side.fighter.name} health`" />
          <p class="hp em-num">HP {{ hpOf(side.key, side.fighter) }} / {{ side.fighter.max_hp }}</p>
          <div class="art">
            <div class="sprite" :class="playback.fx[side.key as 'player' | 'wild'] ? `fx-${playback.fx[side.key as 'player' | 'wild']}` : ''">
              <img v-if="art(side.fighter)" :src="art(side.fighter)!" alt="" draggable="false" />
              <span v-else class="letter" aria-hidden="true">{{ side.fighter.name.slice(0, 1) }}</span>
            </div>
            <span
              v-if="playback.ball[side.key as 'player' | 'wild']"
              class="ball"
              :class="`ball-${playback.ball[side.key as 'player' | 'wild']!.phase}`"
              :style="{ '--tier': `var(--em-tier-${playback.ball[side.key as 'player' | 'wild']!.emblem}, var(--em-tier-common))` }"
              aria-hidden="true"
            />
            <span
              v-if="playback.floating && playback.floating.side === side.key"
              :key="playback.floating.id"
              class="float"
              :class="`float-${playback.floating.tone}`"
              aria-hidden="true"
            >{{ playback.floating.text }}</span>
          </div>
          <p class="stats em-num">Essence {{ side.fighter.essence }} · Speed {{ side.fighter.speed }}</p>
          <ul v-if="effects(side.fighter).length" class="effects">
            <li v-for="text in effects(side.fighter)" :key="text">{{ side.label }} · {{ text }}</li>
          </ul>
        </article>
      </template>
    </div>
  </section>
</template>

<style scoped>
.arena {
  position: relative;
  padding: var(--em-space-5);
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  background:
    radial-gradient(ellipse at 50% 90%, #36424b, transparent 70%),
    linear-gradient(#152332, #101720);
}
.fighters {
  display: grid;
  grid-template-columns: 1fr 60px 1fr;
  align-items: start;
  gap: var(--em-space-5);
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-2);
  margin-bottom: var(--em-space-2);
}
.head h3 {
  margin: 0;
  font-size: 18px;
}
.head small {
  font-size: 12px;
  color: var(--em-muted);
}
.hp {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--em-muted);
}
.art {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 230px;
  margin-top: var(--em-space-3);
}
.sprite {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
.art img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  mix-blend-mode: lighten;
}
.wild .art img {
  transform: scaleX(-1);
}
.letter {
  font-size: 80px;
  font-weight: 600;
  color: var(--em-accent);
}
.versus {
  align-self: center;
  text-align: center;
  font-size: 24px;
  color: var(--em-accent);
}
.stats {
  margin: var(--em-space-2) 0 0;
  font-size: 12px;
  color: var(--em-muted);
}
.effects {
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--em-muted);
}
/* Battle playback: one class per effect, on the picture only. Player faces right, wild left. */
.skip {
  position: absolute;
  top: var(--em-space-2);
  right: var(--em-space-2);
  z-index: 2;
  padding: 4px 12px;
  border: 1px solid var(--em-border);
  background: var(--em-header);
  color: var(--em-text);
  font-size: 12px;
  cursor: pointer;
}
.arena.playing {
  cursor: pointer;
}
.player .sprite {
  --dir: 1;
}
.wild .sprite {
  --dir: -1;
}
.fx-lunge {
  animation: lunge 320ms ease-out;
}
.fx-hit {
  animation: shake 460ms linear;
}
.fx-hit img {
  animation: flash-damage 460ms ease-out;
}
.fx-guarded {
  animation: shake-small 460ms linear;
}
.fx-guarded img {
  animation: glow-defense 460ms ease-out;
}
.fx-guard img {
  animation: glow-defense 700ms ease-in-out;
}
.fx-boost {
  animation: rise 700ms ease-out;
}
.fx-boost img {
  animation: glow-support 700ms ease-in-out;
}
.fx-flee-away {
  animation: flee-away 800ms ease-in forwards;
}
.fx-flee-fail {
  animation: shake-small 600ms linear;
}
.fx-absorb {
  animation: absorb 400ms ease-in forwards;
}
.fx-release {
  animation: release 400ms ease-out;
}
.ball {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 28px;
  height: 28px;
  margin: -14px 0 0 -14px;
  border: 3px solid var(--em-card-ink);
  border-radius: var(--radius-full);
  background: radial-gradient(circle at 35% 30%, #fff8, transparent 40%), var(--tier);
}
.player .ball {
  --from: 220px;
}
.wild .ball {
  --from: -220px;
}
.ball-throw {
  animation: throw 650ms ease-out both;
}
.ball-wobble {
  animation: wobble 333ms ease-in-out 3;
}
.ball-caught {
  animation: caught 800ms ease-out forwards;
}
.ball-open {
  animation: pop 400ms ease-out forwards;
}
.float {
  position: absolute;
  top: 18%;
  left: 50%;
  z-index: 1;
  font-family: var(--em-font-display);
  font-size: 22px;
  white-space: nowrap;
  text-shadow: 0 2px 0 #000a;
  pointer-events: none;
  animation: float 1000ms ease-out forwards;
}
.float-damage {
  color: var(--em-danger);
}
.float-guarded {
  color: var(--em-cat-defense);
}
.float-good {
  color: var(--em-success);
}
.float-bad {
  color: var(--em-warning);
}
.float-info {
  color: var(--em-text);
}
@keyframes lunge {
  40% {
    transform: translateX(calc(var(--dir) * 70px));
  }
}
@keyframes shake {
  0%,
  100% {
    transform: translateX(0);
  }
  15%,
  55% {
    transform: translateX(-12px);
  }
  35%,
  75% {
    transform: translateX(12px);
  }
}
@keyframes shake-small {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-6px);
  }
  75% {
    transform: translateX(6px);
  }
}
@keyframes flash-damage {
  0%,
  60% {
    filter: brightness(1.8) drop-shadow(0 0 10px var(--em-danger));
  }
  100% {
    filter: none;
  }
}
@keyframes glow-defense {
  50% {
    filter: drop-shadow(0 0 18px var(--em-cat-defense)) brightness(1.2);
  }
}
@keyframes glow-support {
  50% {
    filter: drop-shadow(0 0 18px var(--em-cat-support)) brightness(1.2);
  }
}
@keyframes rise {
  50% {
    transform: translateY(-14px);
  }
}
@keyframes flee-away {
  to {
    transform: translateX(calc(var(--dir) * -160px));
    opacity: 0;
  }
}
@keyframes absorb {
  to {
    transform: scale(0.05);
    opacity: 0;
  }
}
@keyframes release {
  from {
    transform: scale(0.05);
    opacity: 0;
  }
}
@keyframes throw {
  from {
    transform: translate(var(--from), 50px) scale(0.6);
  }
  50% {
    transform: translate(calc(var(--from) * 0.4), -70px) scale(1);
  }
  to {
    transform: translate(0, 0) scale(1);
  }
}
@keyframes wobble {
  25% {
    transform: rotate(-24deg);
  }
  75% {
    transform: rotate(24deg);
  }
}
@keyframes caught {
  40% {
    transform: scale(1.4);
    box-shadow: 0 0 22px var(--tier);
  }
  to {
    transform: scale(1);
    box-shadow: 0 0 10px var(--em-success);
  }
}
@keyframes pop {
  to {
    transform: scale(2.2);
    opacity: 0;
  }
}
@keyframes float {
  from {
    transform: translate(-50%, 0);
    opacity: 1;
  }
  to {
    transform: translate(-50%, -56px);
    opacity: 0;
  }
}
@media (max-width: 700px) {
  .arena {
    padding: 18px;
  }
  .fighters {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
  .versus {
    order: 2;
    margin: 12px 0;
    font-size: 18px;
  }
  .wild {
    order: 3;
  }
  .art {
    height: 155px;
  }
}
</style>
