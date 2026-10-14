<script setup lang="ts">
import type { BallPhase } from '../../utils/battleCues';
import EmEmblem from './EmEmblem.vue';

/** Capture playback only; the inventory EMBLEM stays a quiet, engraved stone. */
withDefaults(defineProps<{ tierId: string; phase: BallPhase; strain?: 1 | 2 | 3 }>(), { strain: 1 });
</script>

<template>
  <span class="em-capture-stone" :class="[`ball-${phase}`, `strain-${strain}`]" :style="{ '--tier': `var(--em-tier-${tierId}, var(--em-tier-common))` }" aria-hidden="true">
    <span class="stone-shell">
      <EmEmblem class="stone-whole" :tier-id="tierId" :size="64" />
      <template v-if="phase === 'open'">
        <EmEmblem class="stone-fragment fragment-left" :tier-id="tierId" :size="64" />
        <EmEmblem class="stone-fragment fragment-right" :tier-id="tierId" :size="64" />
      </template>
      <svg class="stone-cracks" viewBox="0 0 64 64" fill="none">
        <path d="M32 32 25 22 28 15 23 7 M32 32 42 24 40 16 47 9 M32 32 22 38 15 35 7 42 M32 32 40 39 38 46 47 56 M32 32 30 43 34 50 29 58" />
      </svg>
      <span class="stone-core" />
      <svg class="stone-seal" viewBox="0 0 64 64" fill="none"><circle cx="32" cy="32" r="21" /><path d="m32 15 5 12 12 5-12 5-5 12-5-12-12-5 12-5Z" /></svg>
    </span>
    <span v-if="phase === 'absorb' || phase === 'open'" class="capture-flow">
      <i v-for="n in 8" :key="n" :style="{ '--angle': `${n * 45}deg`, '--delay': `${(n % 4) * 40}ms` }" />
    </span>
  </span>
</template>

<style scoped>
.em-capture-stone { display:grid; place-items:center; width:64px; height:64px; color:var(--tier); pointer-events:none; }
.stone-shell { position:relative; width:64px; height:64px; }
.stone-shell>.em-emblem { position:absolute; inset:0; }
.stone-cracks,.stone-seal { position:absolute; inset:0; width:100%; height:100%; stroke:currentColor; stroke-width:1.4; opacity:0; filter:drop-shadow(0 0 3px currentColor); }
.stone-cracks { stroke-dasharray:80; stroke-dashoffset:80; }
.stone-core { position:absolute; inset:35%; border-radius:var(--radius-full); opacity:0; background:radial-gradient(circle,#fff 0%,var(--tier) 25%,transparent 70%); }
.ball-throw .stone-shell { animation:stone-throw 650ms ease-out both; }
.ball-absorb .stone-core { animation:core-open 600ms ease-in-out both; }
.ball-absorb .stone-shell { filter:drop-shadow(0 0 10px var(--tier)); }
.ball-wobble { --amp:1; --tug:520ms; }
.ball-wobble.strain-2 { --amp:1.6; --tug:420ms; }
.ball-wobble.strain-3 { --amp:2.2; --tug:320ms; }
.ball-wobble .stone-shell { animation:stone-struggle var(--tug) ease-in-out infinite; filter:drop-shadow(0 0 8px var(--tier)); }
.ball-wobble .stone-cracks { animation:cracks-open var(--tug) ease-in-out infinite alternate; }
.ball-wobble.strain-1 .stone-cracks { opacity:.4; }
.ball-wobble.strain-2 .stone-cracks { opacity:.7; }
.ball-wobble.strain-3 .stone-cracks { opacity:1; }
.ball-still .stone-shell { animation:stone-hush 600ms ease-in-out both; }
.ball-still .stone-cracks { opacity:.8; stroke-dashoffset:0; }
.ball-caught .stone-shell { animation:stone-sealed 800ms ease-out both; }
.ball-caught .stone-cracks { animation:cracks-seal 450ms ease-out both; }
.ball-caught .stone-seal { animation:seal-flash 800ms ease-out both; }
.ball-open .stone-whole { visibility:hidden; }
.stone-fragment { animation:stone-break 700ms ease-out both; }
.fragment-left { clip-path:polygon(0 0,52% 0,44% 26%,55% 48%,43% 69%,52% 100%,0 100%); --split:-1; }
.fragment-right { clip-path:polygon(52% 0,100% 0,100% 100%,52% 100%,43% 69%,55% 48%,44% 26%); --split:1; }
.ball-open .stone-core { animation:core-release 700ms ease-out both; }
.capture-flow { position:absolute; inset:0; }
.capture-flow i { position:absolute; top:50%; left:50%; width:4px; height:4px; margin:-2px; background:var(--tier); box-shadow:0 0 6px var(--tier); opacity:0; }
.ball-absorb .capture-flow i { animation:flow-in 550ms ease-in var(--delay) both; }
.ball-open .capture-flow i { animation:flow-out 500ms ease-out var(--delay) both; }
@keyframes stone-throw { from { transform:translate(var(--from),50px) scale(.6) rotate(-50deg); } 50% { transform:translate(calc(var(--from) * .4),-70px) rotate(-20deg); } to { transform:translate(0,0) rotate(0); } }
@keyframes core-open { 0% { transform:scale(.3); opacity:0; } 40% { transform:scale(1.7); opacity:1; } 100% { transform:scale(.4); opacity:.2; } }
@keyframes flow-in { from { transform:rotate(var(--angle)) translateX(100px) scale(1.3); opacity:0; } 20% { opacity:1; } to { transform:rotate(var(--angle)) translateX(0) scale(.2); opacity:0; } }
@keyframes flow-out { from { transform:rotate(var(--angle)) translateX(0); opacity:1; } to { transform:rotate(var(--angle)) translateX(90px) scale(.2); opacity:0; } }
@keyframes stone-struggle { 0%,100% { transform:rotate(0); } 25% { transform:translateY(calc(var(--amp) * -4px)) rotate(calc(var(--amp) * -8deg)); } 70% { transform:translateY(calc(var(--amp) * -3px)) rotate(calc(var(--amp) * 8deg)); } }
@keyframes cracks-open { from { stroke-dashoffset:65; } to { stroke-dashoffset:0; } }
@keyframes stone-hush { from { transform:scale(1.1); filter:drop-shadow(0 0 8px var(--tier)); } to { transform:scale(1); filter:drop-shadow(0 0 16px var(--tier)); } }
@keyframes cracks-seal { from { opacity:1; stroke-dashoffset:0; } to { opacity:0; stroke-dashoffset:80; } }
@keyframes seal-flash { 0% { opacity:0; transform:scale(.7); } 40% { opacity:1; transform:scale(1); } to { opacity:0; transform:scale(1.25); } }
@keyframes stone-sealed { 40% { transform:scale(1.15); filter:drop-shadow(0 0 20px var(--tier)); } to { transform:scale(1); filter:drop-shadow(0 0 6px var(--tier)); } }
@keyframes stone-break { from { transform:translateX(0); opacity:1; } to { transform:translate(calc(var(--split) * 36px),20px) rotate(calc(var(--split) * 28deg)); opacity:0; } }
@keyframes core-release { 0% { opacity:1; transform:scale(.3); } 40% { opacity:.9; transform:scale(3); } to { opacity:0; transform:scale(4); } }
@media(prefers-reduced-motion:reduce) {
  .em-capture-stone * { animation:none !important; }
  .capture-flow,.stone-core,.stone-cracks,.stone-seal { display:none; }
  .ball-absorb .stone-shell,.ball-caught .stone-shell { filter:drop-shadow(0 0 8px var(--tier)); }
  .fragment-left { transform:translateX(-5px); } .fragment-right { transform:translateX(5px); }
}
</style>
