<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { titleCase, type StatLine } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import TypeSymbol from "./ui/TypeSymbol.vue";
import ascensionLogo from "../assets/brand/ascension-logo-icon.webp";
const frameAssets = import.meta.glob<string>("../assets/ascended_card/ascended_card_front_*.webp", { eager: true, query: "?url", import: "default" });
const backAssets = import.meta.glob<string>("../assets/ascended_card/ascended_card_back_*.webp", { eager: true, query: "?url", import: "default" });
const props = withDefaults(defineProps<{ ascended: AscendedInfo; level?: number; tierId?: string; stars?: number; stats?: StatLine[]; showLevel?: boolean; flipped?: boolean; artSlot?: "battle" | "preview_card" }>(), { level: 1, tierId: "common", stars: undefined, stats: undefined, showLevel: false, flipped: false, artSlot: "battle" });
const artUrl = computed(() => props.artSlot === "preview_card" ? props.ascended.art?.preview_card : spriteFor(props.ascended.art, "battle"));
const tierVar = computed(() => `var(--em-tier-${props.tierId}, var(--em-tier-common))`);
const types = computed(() => props.ascended.ascension_types);
const frameUrl = computed(() => frameAssets[`../assets/ascended_card/ascended_card_front_${props.tierId}.webp`] ?? frameAssets["../assets/ascended_card/ascended_card_front_common.webp"]);
const backUrl = computed(() => backAssets[`../assets/ascended_card/ascended_card_back_${props.tierId}.webp`] ?? backAssets["../assets/ascended_card/ascended_card_back_common.webp"]);
</script>
<template>
  <article class="card" :class="[`tier-${tierId}`, { flipped, 'preview-art': artSlot === 'preview_card' }]" :style="{ '--tier': tierVar }" :aria-label="flipped ? 'Uncollected Ascended' : `${ascended.name}, ${titleCase(tierId)}, level ${level}`">
    <img v-if="!flipped" class="tier-frame" :src="frameUrl" alt="" aria-hidden="true" draggable="false" />
    <div v-if="!flipped" class="face front">
      <div class="art" aria-hidden="true"><img v-if="artUrl" class="portrait" :src="artUrl" alt="" draggable="false" /><span v-else class="letter">{{ ascended.name.slice(0, 1) }}</span><dl v-if="stats" class="stats"><div v-for="stat in stats" :key="stat.key"><dt>{{ stat.label }}</dt><dd class="em-num">{{ stat.value }}</dd></div></dl></div>
      <header class="header"><h4 class="ascended-name">{{ ascended.name }}</h4><span v-if="showLevel" class="level">Lv {{ level }}</span></header>
      <footer class="card-meta"><span v-if="stars !== undefined" class="stars em-num" :aria-label="`${stars} stars`">★ {{ stars }}</span><div class="front-types"><TypeSymbol v-for="id in types" :key="id" :type-id="id" size="12cqw" :flat="types.length > 1" /></div></footer>
    </div>
    <div v-if="flipped" class="face card-back concealed"><img class="tier-back" :src="backUrl" alt="" aria-hidden="true" draggable="false" /><div class="back-brand" aria-hidden="true"><img class="back-logo" :src="ascensionLogo" alt="" draggable="false" /></div><span class="unknown">UNCOLLECTED</span></div>
  </article>
</template>
<style scoped>
.card { container-type: inline-size; position: relative; width: var(--card-width, var(--em-preview-card-width, 160px)); min-width:var(--em-preview-card-width, 160px); flex-shrink:0; aspect-ratio: 265 / 371; padding: 0; border: 0; background: transparent; color: #f4f1e8; text-align: center; }
.tier-frame,.tier-back { position:absolute; inset:0; width:100%; height:100%; object-fit:fill; image-rendering:pixelated; pointer-events:none; }
.tier-frame { z-index:3; }
.front { position:absolute; inset:6% 8%; border-radius:var(--radius-sm); overflow:hidden; display:flex; flex-direction:column; background:#0b1b28; }
.art { position:relative; display:flex; align-items:center; justify-content:center; flex:1; min-height:0; overflow:hidden; background: radial-gradient(ellipse at 50% 70%,color-mix(in srgb,var(--tier) 38%,#0b1927),color-mix(in srgb,var(--tier) 10%,#0b1927) 75%); border-bottom:2px solid #647c8e; }
.art::after { content:""; position:absolute; inset:auto 8% 4%; height:6%; border-radius:var(--radius-full); background:#0007; filter:blur(3px); }
.stats { position:absolute; inset:auto 0 0; z-index:2; display:flex; justify-content:space-between; gap:1cqw; margin:0; padding:5cqw 4cqw 2cqw; background:linear-gradient(transparent,#0b1b28cc 40%); }
.stats div { min-width:0; } .stats dt { font-size:4cqw; color:#c5d2dc; } .stats dd { margin:0; font-size:7.5cqw; font-weight:700; line-height:1.1; }
.portrait { width:100%; height:100%; position:absolute; inset:0; padding:6% 4% 3%; object-fit:contain; image-rendering:pixelated; z-index:1; }
.preview-art .portrait { padding:0; }
.letter { font:30cqw var(--em-font-display); color:var(--em-accent); }
.header { display:flex; justify-content:center; align-items:center; gap:3cqw; padding:5cqw 2cqw 1cqw; }
.ascended-name { margin:0; font:clamp(10px,6.4cqw,18px) var(--em-font-display); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.level { font-size:5cqw; color:var(--em-accent); flex:none; }
.card-meta { display:flex; align-items:center; justify-content:space-between; padding:1cqw 5cqw 4cqw; min-height:16cqw; }
.stars { font-size:6cqw; color:var(--em-accent); } .front-types { display:flex; gap:2cqw; }
.card > .card-back { position:absolute; inset:0; }
.back-brand { position:absolute; left:35%; top:44%; transform:translateY(-50%); width:30%; pointer-events:none; }
.back-logo { display:block; width:100%; height:auto; object-fit:contain; }
.unknown { position:absolute; left:12%; right:12%; top:83%; transform:translateY(-50%); font:5cqw var(--em-font-display); color:#e3e9ef; text-shadow:0 1px 2px #000; }
</style>
