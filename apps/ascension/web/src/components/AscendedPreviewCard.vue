<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { titleCase, type StatLine } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import TypeSymbol from "./ui/TypeSymbol.vue";
const props = withDefaults(defineProps<{ ascended: AscendedInfo; level?: number; tierId?: string; stars?: number; stats?: StatLine[]; showLevel?: boolean; flipped?: boolean }>(), { level: 1, tierId: "common", stars: undefined, stats: undefined, showLevel: false, flipped: false });
const artUrl = computed(() => spriteFor(props.ascended.art, "battle"));
const tierVar = computed(() => `var(--em-tier-${props.tierId}, var(--em-tier-common))`);
const types = computed(() => props.ascended.ascension_types);
function symbolSize(count: number): string { return count <= 1 ? "30cqw" : count === 2 ? "21cqw" : "15cqw"; }
</script>
<template>
  <article class="card" :class="[`tier-${tierId}`, { flipped }]" :style="{ '--tier': tierVar }" :aria-label="flipped ? 'Uncollected Ascended' : `${ascended.name}, ${titleCase(tierId)}, level ${level}`">
    <span class="gem top" aria-hidden="true"></span><span class="gem bottom" aria-hidden="true"></span>
    <div v-if="!flipped" class="face front">
      <div class="art" aria-hidden="true"><img v-if="artUrl" class="portrait" :src="artUrl" alt="" draggable="false" /><span v-else class="letter">{{ ascended.name.slice(0, 1) }}</span><dl v-if="stats" class="stats"><div v-for="stat in stats" :key="stat.key"><dt>{{ stat.label }}</dt><dd class="em-num">{{ stat.value }}</dd></div></dl></div>
      <header class="header"><h4 class="ascended-name">{{ ascended.name }}</h4><span v-if="showLevel" class="level">Lv {{ level }}</span></header>
      <footer class="card-meta"><span v-if="stars !== undefined" class="stars em-num" :aria-label="`${stars} stars`">★ {{ stars }}</span><div class="front-types"><TypeSymbol v-for="id in types" :key="id" :type-id="id" size="12cqw" :flat="types.length > 1" /></div></footer>
    </div>
    <div class="face card-back" :class="{ concealed: flipped }" :aria-hidden="!flipped"><span class="seal" aria-hidden="true">✦</span><div class="types"><TypeSymbol v-for="id in types" :key="id" :type-id="id" :size="symbolSize(types.length)" :flat="types.length > 1" decorative /></div><span v-if="flipped" class="unknown">UNCOLLECTED</span></div>
  </article>
</template>
<style scoped>
.card { container-type: inline-size; border-radius: var(--radius-lg); position: relative; width: var(--card-width, 150px); aspect-ratio: 265 / 371; padding: 5px; border: 2px solid var(--tier); background: linear-gradient(135deg,color-mix(in srgb,var(--tier) 70%,#fff),color-mix(in srgb,var(--tier) 40%,#1a1208) 12%,color-mix(in srgb,var(--tier) 14%,#0a1520) 50%,color-mix(in srgb,var(--tier) 65%,#000)); box-shadow: inset 0 0 0 2px #091421,inset 0 0 0 3px color-mix(in srgb,var(--tier) 55%,transparent),0 5px 0 #040c13,0 12px 20px #0007; color: #f4f1e8; text-align: center; }
.card::before,.card::after { content:""; position:absolute; z-index:2; width:13%; height:8%; border:3px solid var(--tier); pointer-events:none; }
.gem { position:absolute; left:50%; z-index:3; width:7cqw; height:7cqw; background:var(--tier); border:1px solid #091421; pointer-events:none; }
.gem.top { top:0; transform:translate(-50%,-50%) rotate(45deg); } .gem.bottom { bottom:0; transform:translate(-50%,50%) rotate(45deg); }
.card::before { top:0; left:0; border-right:0; border-bottom:0; border-top-left-radius:var(--radius-lg); } .card::after { right:0; bottom:0; border-left:0; border-top:0; border-bottom-right-radius:var(--radius-lg); }
.front { border-radius: calc(var(--radius-lg) - 6px); overflow:hidden; display:flex; height:100%; flex-direction:column; background:#0b1b28; border:1px solid color-mix(in srgb,var(--tier) 60%,#0b1b28); }
.art { position:relative; display:flex; align-items:center; justify-content:center; flex:1; min-height:0; overflow:hidden; background: radial-gradient(ellipse at 50% 70%,color-mix(in srgb,var(--tier) 38%,#0b1927),color-mix(in srgb,var(--tier) 10%,#0b1927) 75%); border-bottom:2px solid #647c8e; }
.art::after { content:""; position:absolute; inset:auto 8% 4%; height:6%; border-radius:var(--radius-full); background:#0007; filter:blur(3px); }
.stats { position:absolute; inset:auto 0 0; z-index:2; display:flex; justify-content:space-between; gap:1cqw; margin:0; padding:5cqw 4cqw 2cqw; background:linear-gradient(transparent,#0b1b28cc 40%); }
.stats div { min-width:0; } .stats dt { font-size:4cqw; color:#c5d2dc; } .stats dd { margin:0; font-size:7.5cqw; font-weight:700; line-height:1.1; }
.portrait { width:100%; height:100%; position:absolute; inset:0; padding:6% 4% 3%; object-fit:contain; image-rendering:pixelated; z-index:1; }
.letter { font:30cqw var(--em-font-display); color:var(--em-accent); }
.header { display:flex; justify-content:center; align-items:center; gap:3cqw; padding:5cqw 2cqw 1cqw; }
.ascended-name { margin:0; font:clamp(10px,6.4cqw,18px) var(--em-font-display); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.level { font-size:5cqw; color:var(--em-accent); flex:none; }
.card-meta { display:flex; align-items:center; justify-content:space-between; padding:1cqw 5cqw 4cqw; min-height:16cqw; }
.stars { font-size:6cqw; color:var(--em-accent); } .front-types { display:flex; gap:2cqw; }
.card > .card-back { border-radius:calc(var(--radius-lg) - 6px); position:absolute; inset:4cqw; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8cqw; background: repeating-linear-gradient(45deg,#102230,#102230 8px,#142b3b 8px,#142b3b 10px); border:1px solid #607d92; visibility:hidden; }
.card > .card-back.concealed { visibility:visible; } .seal { font-size:25cqw; color:var(--em-accent); } .types { display:flex; flex-wrap:wrap; justify-content:center; gap:4cqw; } .unknown { font:5cqw var(--em-font-display); color:var(--em-muted); }
</style>
