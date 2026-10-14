<script setup lang="ts">
import { computed, ref } from "vue";
import type { AscendedInfo, BattleView, Buff, Fighter } from "../api/AscensionClient";
import { usePlaybackStore } from "../stores/playback";
import { useAscensionStore } from "../stores/ascension";
import { passiveText, statusText } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import EmBar from "./ui/EmBar.vue";
import EmEmblem from "./ui/EmEmblem.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";
import TypeSymbol from "./ui/TypeSymbol.vue";

/** Both Ascended facing each other across a VS marker: name, level, tier, health, their
 * portrait, and what is affecting them (buffs, defense). The numbers are always written. */
const props = defineProps<{ battle: Pick<BattleView, 'player' | 'wild' | 'round'>; preview?: boolean; fighterInfos?: AscendedInfo[] }>();
const playbackStore = usePlaybackStore();
const playback = computed(() => props.preview ? {
  busy: false, hp: null, ball: { player: null, wild: null }, fx: { player: null, wild: null }, floating: null,
} : playbackStore);
const ascension = useAscensionStore();
const failedImages = ref<string[]>([]);

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
  return playback.value.hp?.[key as "player" | "wild"] ?? fighter.hp;
}

/** The fighter's Ascension Types, from the catalog (a battle view does not carry them). */
function typesOf(fighter: Fighter): string[] {
  return infoOf(fighter)?.ascension_types ?? [];
}

function infoOf(fighter: Fighter) {
  return props.fighterInfos?.find(a => a.id === fighter.ascended_id)
    ?? ascension.catalog?.ascendeds.find(a => a.id === fighter.ascended_id);
}
function artInfo(fighter: Fighter) {
  return infoOf(fighter)?.art;
}

function art(fighter: Fighter): string | null {
  const url = spriteFor(artInfo(fighter), "battle");
  return url && !failedImages.value.includes(url) ? url : null;
}

</script>

<template>
  <section class="arena em-glow" :class="{ playing: playback.busy, preview }" :aria-label="preview ? 'Battle preview' : `Round ${battle.round}`">
    <p class="round-number em-pixel">{{ preview ? 'VS' : `Round ${battle.round}` }}</p>
    <div class="fighters">
      <template v-for="side in sides" :key="side.key">

        <article class="fighter" :class="side.key" :aria-label="`${side.label}: ${side.fighter.name}`">
          <div class="head"><EmEmblem v-if="side.fighter.ascended_id" class="fighter-emblem" :tier-id="side.fighter.tier_id" :size="42" />
            <h3><span class="ascended-name">{{ side.fighter.name }}</span> <small v-if="side.fighter.ascended_id" class="em-num">Lv. {{ side.fighter.level }}</small></h3>
            <span v-if="side.fighter.ascended_id" class="badges">
              <TypeSymbol v-for="id in typesOf(side.fighter)" :key="id" :type-id="id" :size="28" />
              <EmTierBadge :tier-id="side.fighter.tier_id" />
            </span>
          </div>
          <div class="art">
            <div v-if="side.fighter.ascended_id" class="health"><EmBar kind="hp" :value="hpOf(side.key, side.fighter)" :max="side.fighter.max_hp" :label="`${side.fighter.name} health`" />
              <p class="hp em-num">HP {{ hpOf(side.key, side.fighter) }} / {{ side.fighter.max_hp }}</p></div>
            <div v-if="!side.fighter.ascended_id" class="no-fighter">Choose a fighter</div>
            <div v-else class="sprite" :class="[{ concealed: ['wobble', 'still', 'caught'].includes(playback.ball[side.key as 'player' | 'wild']?.phase ?? '') },playback.fx[side.key as 'player' | 'wild'] ? `fx-${playback.fx[side.key as 'player' | 'wild']}` : '']">
              <img v-if="art(side.fighter)" :src="art(side.fighter)!" alt="" draggable="false" @error="failedImages.push(art(side.fighter)!)" />
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
          <p v-if="side.fighter.ascended_id" class="stats em-num">Power {{ side.fighter.power }} · Speed {{ side.fighter.speed }}</p>
          <ul v-if="side.fighter.passives?.length" class="passives" :aria-label="`${side.fighter.name} passive effects`">
            <li v-for="(passive, index) in side.fighter.passives" :key="index">{{ passiveText(passive.kind, passive.params) }}</li>
          </ul>
          <ul v-if="effects(side.fighter).length" class="effects">
            <li v-for="text in effects(side.fighter)" :key="text">{{ side.label }} · {{ text }}</li>
          </ul>
        </article>
      </template>
    </div>
  </section>
</template>

<style scoped>
.arena{position:relative;overflow:hidden;padding:20px 34px 10px;border:1px solid var(--em-divider);background:linear-gradient(#06121c22,#06121c11),var(--em-battle-scene,var(--em-forge-scene));background-position:center;background-size:cover;box-shadow:inset 0 0 0 3px #0a111b;min-height:390px}.round-number{position:absolute;top:18px;left:50%;transform:translateX(-50%);font-size:18px;text-shadow:0 2px #000}.fighters{display:grid;grid-template-columns:1fr 1fr;gap:22%;align-items:start}.fighter{min-width:0;position:relative}.head{display:flex;align-items:center;gap:10px;min-height:48px}.fighter-emblem{flex:none}.head h3{margin:0;font-size:16px}.head small{display:block;font-size:12px;color:var(--em-muted);margin-top:4px}.badges{display:flex;gap:5px;align-items:center}.badges :deep(.em-tier){font-size:10px}.wild .head{justify-content:flex-end;text-align:left}.health{position:absolute;top:0;left:0;right:0;z-index:2;margin:0}.health :deep(.em-bar.hp){height:21px;border:1px solid #a6bacb;border-radius:var(--em-radius);box-shadow:inset 0 0 0 2px #071019}.hp{position:absolute;inset:0;text-align:center;font-size:12px;line-height:21px;color:#fff;font-weight:700;text-shadow:0 1px 2px #000}.art{position:relative;display:flex;align-items:end;justify-content:center;height:285px;margin-top:12px}.sprite{display:flex;align-items:end;justify-content:center;width:100%;height:100%}.sprite.concealed{visibility:hidden}.art img{max-width:100%;max-height:calc(100% - 34px);object-fit:contain;image-rendering:pixelated;mix-blend-mode:lighten}.wild .art img{transform:scaleX(-1)}.letter{font:80px var(--em-font-display);color:var(--em-accent)}.stats{font-size:11px;color:var(--em-muted);margin-top:8px;text-shadow:0 1px #000}.effects{position:absolute;top:94px;left:0;z-index:1;margin:0;padding:0;list-style:none;font-size:10px}.effects li{background:#081522dd;padding:3px 6px;margin-top:4px;border:1px solid var(--em-divider)}
/* Battle playback: one class per effect, on the picture only. Player faces right, wild left. */
.player .sprite {
  --dir: 1;
}
.passives { margin: 6px 0 0; padding: 0; list-style: none; color: var(--em-muted); font-size: 11px; line-height: 1.5; text-shadow: 0 1px #000; }
.passives li + li { margin-top: 4px; }
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

@media(max-width:700px){.arena{padding:45px 10px 10px;min-height:315px}.round-number{top:12px;font-size:15px}.fighters{gap:8%}.head,.wild .head{flex-direction:column;align-items:flex-start;gap:4px;text-align:left;min-height:72px}.head h3{font-size:13px}.badges :deep(img){max-width:22px;max-height:22px}.health :deep(.em-bar.hp){height:19px}.hp{font-size:10px;line-height:19px}.art{height:195px}.stats{font-size:10px}.effects{top:122px;max-width:100%;font-size:9px}.ball{transform:scale(.8)}}
.no-fighter{align-self:center;color:var(--em-muted);font-size:13px}.health :deep(.fill){background:linear-gradient(#7ab788,#3d8d55)}.wild .health :deep(.fill){background:linear-gradient(#db6576,#a12d40)}
.arena { border:0; background:linear-gradient(180deg,#03132100,#03132166); box-shadow:none; padding:20px 24px 16px; min-height:420px; }
.fighters { gap:14%; }
.head { flex-wrap:wrap; min-height:70px; gap:8px; }
.head h3 { font-size:16px; }
.fighter-emblem { width:30px; height:30px; }
.badges :deep(img) { max-width:22px; max-height:22px; }
.health :deep(.em-bar.hp) { border:0; box-shadow:none; height:16px; }
.hp { font-size:10px; line-height:16px; }
.round-number { font:700 20px var(--em-font-heading); }
@media(orientation:portrait), (max-width:700px) {
 .arena { min-height:330px; padding:32px 4px 12px; }
 .fighters { gap:16px; }
 .head,.wild .head { flex-direction:row; align-content:start; align-items:center; gap:5px; min-height:88px; justify-content:start; }
 .head h3 { font-size:12px; } .head small { font-size:10px; }
 .badges { flex-wrap:wrap; gap:4px; } .badges :deep(.em-tier) { font-size:9px; }
 .fighter-emblem { width:24px; height:24px; }
 .art { height:210px; }
 .health :deep(.em-bar.hp) { height:16px; }
 .hp { font-size:9px; line-height:16px; }
 .stats { font-size:10px; }
}
</style>
