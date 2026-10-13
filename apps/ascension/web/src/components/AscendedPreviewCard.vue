<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { titleCase } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import TypeSymbol from "./ui/TypeSymbol.vue";
const props = withDefaults(defineProps<{ ascended: AscendedInfo; level?: number; tierId?: string; showLevel?: boolean; flipped?: boolean }>(), { level: 1, tierId: "common", showLevel: false, flipped: false });
const artUrl = computed(() => spriteFor(props.ascended.art, "battle"));
const tierVar = computed(() => `var(--em-tier-${props.tierId}, var(--em-tier-common))`);
const types = computed(() => props.ascended.ascension_types);
function symbolSize(count: number): string { return count <= 1 ? "30cqw" : count === 2 ? "21cqw" : "15cqw"; }
</script>
<template>
  <article class="card" :class="[`tier-${tierId}`, { flipped }]" :style="{ '--tier': tierVar }" :aria-label="flipped ? 'Uncollected Ascended' : `${ascended.name}, ${titleCase(tierId)}, level ${level}`">
    <div v-if="!flipped" class="face front">
      <div class="art" aria-hidden="true"><img v-if="artUrl" class="portrait" :src="artUrl" alt="" draggable="false" /><span v-else class="letter">{{ ascended.name.slice(0, 1) }}</span></div>
      <header class="header"><h4 class="ascended-name">{{ ascended.name }}</h4><span v-if="showLevel" class="level">Lv {{ level }}</span></header>
      <footer class="card-meta"><span class="tier">{{ titleCase(tierId) }}</span><div class="front-types"><TypeSymbol v-for="id in types" :key="id" :type-id="id" size="12cqw" :flat="types.length > 1" /></div></footer>
    </div>
    <div class="face card-back" :class="{ concealed: flipped }" :aria-hidden="!flipped"><span class="seal" aria-hidden="true">✦</span><div class="types"><TypeSymbol v-for="id in types" :key="id" :type-id="id" :size="symbolSize(types.length)" :flat="types.length > 1" decorative /></div><span v-if="flipped" class="unknown">UNCOLLECTED</span></div>
  </article>
</template>
<style scoped>
.card { container-type: inline-size; position: relative; width: var(--card-width, 150px); aspect-ratio: 265 / 371; padding: 5px; border: 2px solid #7593a6; background: linear-gradient(135deg,#bad0dc,#314a60 12%,#122331 50%,#8ca8ba); box-shadow: inset 0 0 0 2px #091421,0 5px 0 #040c13,0 12px 20px #0007; color: #f4f1e8; text-align: center; }
.card::before,.card::after { content:""; position:absolute; z-index:2; width:13%; height:8%; border:2px solid var(--em-accent); pointer-events:none; }
.card::before { top:0; left:0; border-right:0; border-bottom:0; } .card::after { right:0; bottom:0; border-left:0; border-top:0; }
.front { display:flex; height:100%; flex-direction:column; background:#0b1b28; border:1px solid #8ca5b6; }
.art { position:relative; display:flex; align-items:center; justify-content:center; flex:1; min-height:0; overflow:hidden; background: radial-gradient(ellipse at 50% 70%,#334555,#0b1927 75%); border-bottom:2px solid #647c8e; }
.art::after { content:""; position:absolute; inset:auto 8% 4%; height:6%; border-radius:var(--radius-full); background:#0007; filter:blur(3px); }
.portrait { width:100%; height:100%; position:absolute; inset:0; padding:6% 4% 3%; object-fit:contain; image-rendering:pixelated; z-index:1; }
.letter { font:30cqw var(--em-font-display); color:var(--em-accent); }
.header { display:flex; justify-content:center; align-items:center; gap:3cqw; padding:5cqw 2cqw 1cqw; }
.ascended-name { margin:0; font:clamp(10px,6.4cqw,18px) var(--em-font-display); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.level { font-size:5cqw; color:var(--em-accent); flex:none; }
.card-meta { display:flex; align-items:center; justify-content:space-between; padding:1cqw 5cqw 4cqw; min-height:16cqw; }
.tier { font-size:6cqw; color:var(--tier); } .front-types { display:flex; gap:2cqw; }
.card > .card-back { position:absolute; inset:4cqw; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8cqw; background: repeating-linear-gradient(45deg,#102230,#102230 8px,#142b3b 8px,#142b3b 10px); border:1px solid #607d92; visibility:hidden; }
.card > .card-back.concealed { visibility:visible; } .seal { font-size:25cqw; color:var(--em-accent); } .types { display:flex; flex-wrap:wrap; justify-content:center; gap:4cqw; } .unknown { font:5cqw var(--em-font-display); color:var(--em-muted); }
</style>
