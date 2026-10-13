<script setup lang="ts">
import { computed } from "vue";
import type { BattleView, Buff, Fighter, Side } from "../api/AscensionClient";
import { usePlaybackStore } from "../stores/playback";
import { useAscensionStore } from "../stores/ascension";
import { statusText } from "../utils/ascension";
import { poseFor, spriteFor } from "../utils/sprites";
import { other } from "../utils/battleCues";
import AnimatedSprite from "./ui/AnimatedSprite.vue";
import EmBar from "./ui/EmBar.vue";
import EmEmblem from "./ui/EmEmblem.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";
import TypeSymbol from "./ui/TypeSymbol.vue";

/** Both Ascended facing each other across a VS marker: name, level, tier, health, their
 * portrait, and what is affecting them (buffs, defense). The numbers are always written. */
const props = defineProps<{ battle: BattleView }>();
const playback = usePlaybackStore();
const ascension = useAscensionStore();

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
  for (const status of fighter.statuses ?? []) list.push(statusText(status));
  return list;
}

/** The health to draw: the old value until a playing hit lands. */
function hpOf(key: string, fighter: Fighter): number {
  return playback.hp?.[key as "player" | "wild"] ?? fighter.hp;
}

/** The fighter's Ascension Types, from the catalog (a battle view does not carry them). */
function typesOf(fighter: Fighter): string[] {
  return ascension.catalog?.ascendeds.find((a) => a.id === fighter.ascended_id)?.ascension_types ?? [];
}

function artInfo(fighter: Fighter) {
  return ascension.catalog?.ascendeds.find((a) => a.id === fighter.ascended_id)?.art;
}

function art(fighter: Fighter): string | null {
  return spriteFor(artInfo(fighter), "battle");
}

/** The fighter's sheet, if it has one; the rest keep their still battle sprite. */
function sheet(fighter: Fighter) {
  return artInfo(fighter)?.animation ?? null;
}

/** What the fighter does now: its effect, or catching while an EMBLEM is thrown at the other side. */
function pose(key: string) {
  const side = key as Side;
  return poseFor(playback.fx[side], playback.ball[other(side)]?.phase === "throw");
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
            <span class="badges">
              <TypeSymbol v-for="id in typesOf(side.fighter)" :key="id" :type-id="id" :size="28" />
              <EmTierBadge :tier-id="side.fighter.tier_id" />
            </span>
          </div>
          <EmBar kind="hp" :value="hpOf(side.key, side.fighter)" :max="side.fighter.max_hp" :label="`${side.fighter.name} health`" />
          <p class="hp em-num">HP {{ hpOf(side.key, side.fighter) }} / {{ side.fighter.max_hp }}</p>
          <div class="art">
            <div class="sprite" :class="[playback.fx[side.key as 'player' | 'wild'] ? `fx-${playback.fx[side.key as 'player' | 'wild']}` : '']">
              <span v-if="sheet(side.fighter)" class="pic"><AnimatedSprite :sheet="sheet(side.fighter)!" :state="pose(side.key)" /></span>
              <img v-else-if="art(side.fighter)" :src="art(side.fighter)!" alt="" draggable="false" />
              <span v-else class="letter" aria-hidden="true">{{ side.fighter.name.slice(0, 1) }}</span>
            </div>
            <span
              v-if="playback.ball[side.key as 'player' | 'wild']"
              class="ball"
              :class="[`ball-${playback.ball[side.key as 'player' | 'wild']!.phase}`, playback.ball[side.key as 'player' | 'wild']!.strain ? `strain-${playback.ball[side.key as 'player' | 'wild']!.strain}` : '']"
              :style="{ '--tier': `var(--em-tier-${playback.ball[side.key as 'player' | 'wild']!.emblem}, var(--em-tier-common))` }"
              aria-hidden="true"
            ><EmEmblem :tier-id="playback.ball[side.key as 'player' | 'wild']!.emblem" :size="52" /></span>
            <span
              v-if="playback.floating && playback.floating.side === side.key"
              :key="playback.floating.id"
              class="float"
              :class="`float-${playback.floating.tone}`"
              aria-hidden="true"
            >{{ playback.floating.text }}</span>
          </div>
          <p class="stats em-num">Power {{ side.fighter.power }} · Speed {{ side.fighter.speed }}</p>
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
.badges {
  display: flex;
  align-items: center;
  gap: 6px;
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
.pic {
  display: flex;
  height: 100%;
  max-width: 100%;
}
.wild .art img,
.wild .pic {
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
.fx-hit img,
.fx-hit .pic {
  animation: flash-damage 460ms ease-out;
}
.fx-guarded {
  animation: shake-small 460ms linear;
}
.fx-guarded img,
.fx-guarded .pic {
  animation: glow-defense 460ms ease-out;
}
.fx-guard img,
.fx-guard .pic {
  animation: glow-defense 700ms ease-in-out;
}
.fx-boost {
  animation: rise 700ms ease-out;
}
.fx-boost img,
.fx-boost .pic {
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
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin: -26px 0 0 -26px;
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
/* The Ascended fights the EMBLEM: three tugs, each harder and longer, then a held breath. */
.ball-wobble,
.ball-still {
  filter: drop-shadow(0 0 8px var(--tier));
}
.ball-wobble::after {
  position: absolute;
  inset: -3px;
  border: 2px solid var(--em-danger);
  border-radius: var(--radius-full);
  content: "";
  opacity: 0;
  animation: strain-ring 450ms ease-out infinite;
}
.strain-1 {
  --amp: 1;
  animation: ball-struggle 520ms ease-in-out infinite;
}
.strain-2 {
  --amp: 1.6;
  animation: ball-struggle 420ms ease-in-out infinite;
}
.strain-3 {
  --amp: 2.2;
  animation: ball-struggle 320ms ease-in-out infinite;
}
.ball-still {
  animation: hush 600ms ease-in-out both;
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
/* The EMBLEM pulses in size, bounces and rotates as the Ascended fights it; --amp grows each tug. */
@keyframes ball-struggle {
  0%, 100% { transform: translateY(0) scale(1) rotate(0); }
  20% { transform: translateY(calc(var(--amp) * -8px)) scale(calc(1 + var(--amp) * 0.12)) rotate(calc(var(--amp) * -14deg)); }
  50% { transform: translateY(0) scale(calc(1 - var(--amp) * 0.04)) rotate(0); }
  70% { transform: translateY(calc(var(--amp) * -6px)) scale(calc(1 + var(--amp) * 0.1)) rotate(calc(var(--amp) * 14deg)); }
}
@keyframes hush {
  0% { transform: scale(1.3); filter: drop-shadow(0 0 8px var(--tier)); }
  50% { transform: scale(1.12); filter: drop-shadow(0 0 16px var(--tier)); }
  100% { transform: scale(1.2); filter: drop-shadow(0 0 24px var(--tier)); }
}
@keyframes strain-ring {
  from { transform: scale(1); opacity: 0.9; }
  to { transform: scale(2.2); opacity: 0; }
}
@keyframes caught {
  40% {
    transform: scale(1.4);
    filter: drop-shadow(0 0 18px var(--tier));
  }
  to {
    transform: scale(1);
    filter: drop-shadow(0 0 10px var(--em-success));
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
    padding: var(--em-space-3);
  }
  .fighters {
    position: relative;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--em-space-2);
  }
  .versus {
    position: absolute;
    top: 50%;
    left: 50%;
    z-index: 1;
    transform: translate(-50%, -50%);
    font-size: 14px;
    text-shadow: 0 2px 0 #000a;
  }
  .head {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    margin-bottom: 4px;
  }
  .head h3 {
    max-width: 100%;
    overflow: hidden;
    font-size: 14px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badges :deep(svg),
  .badges :deep(img) {
    max-width: 20px;
    max-height: 20px;
  }
  .hp {
    margin-top: 2px;
    font-size: 11px;
  }
  .art {
    height: 110px;
    margin-top: var(--em-space-2);
  }
  .stats,
  .effects {
    font-size: 11px;
  }
}
</style>
