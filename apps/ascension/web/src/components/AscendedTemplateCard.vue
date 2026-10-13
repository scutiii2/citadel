<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { abilityEffect, passiveText, titleCase } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import TypeSymbol from "./ui/TypeSymbol.vue";
const props = withDefaults(defineProps<{ ascended: AscendedInfo; level?: number; tierId?: string }>(), { level: 1, tierId: "common" });
const artUrl = computed(() => spriteFor(props.ascended.art, "battle"));
const tierVar = computed(() => `var(--em-tier-${props.tierId}, var(--em-tier-common))`);
const passiveName = computed(() => titleCase(props.ascended.passive.kind));
const passive = computed(() => passiveText(props.ascended.passive.kind, props.ascended.passive.params));
const stats = computed(() => ([{ key: "hp", label: "HP" }, { key: "power", label: "Power" }, { key: "speed", label: "Speed" }] as const).map(s => ({ ...s, value: props.ascended.base[s.key] ?? 0, growth: props.ascended.growth[s.key] ?? 0 })));
</script>
<template>
  <article class="card" :class="`tier-${tierId}`" :style="{ '--tier': tierVar }" :aria-label="`${ascended.name}, ${titleCase(tierId)}, level ${level}`">
    <header class="header"><h4 class="ascended-name">{{ ascended.name }}</h4><span class="level">Lv {{ level }}</span></header>
    <div class="art-fill" aria-hidden="true"><img v-if="artUrl" class="portrait" :src="artUrl" style="object-position:50% 50%" alt="" draggable="false" /><span v-else class="letter">{{ ascended.name.slice(0, 1) }}</span></div>
    <div class="card-meta"><span class="tier">{{ titleCase(tierId) }}</span><div class="types"><TypeSymbol v-for="id in ascended.ascension_types" :key="id" :type-id="id" size="28px" :flat="ascended.ascension_types.length > 1" /></div></div>
    <dl class="stat-list"><div v-for="s in stats" :key="s.key" class="stat"><dt>{{ s.label }}</dt><dd>{{ s.value }}</dd><span class="growth">+{{ s.growth }} / lvl</span></div></dl>
    <p class="passive" :title="`${passiveName}: ${passive}`"><strong>{{ passiveName }}</strong><template v-if="passive !== passiveName">{{ ` ${passive}` }}</template></p>
    <div class="ability-list"><div v-for="a in ascended.abilities.slice(0, 3)" :key="a.id" class="ability" :class="a.category.toLowerCase()"><div class="ability-text"><strong>{{ a.name }}</strong><span>{{ abilityEffect(a) }}</span></div><span class="unlock">Lv {{ a.unlock_level }}</span></div></div>
  </article>
</template>
<style scoped>
.card { position:relative; width:var(--card-width,440px); max-width:100%; padding:12px; border:3px solid #7894a7; color:var(--em-text); background:linear-gradient(135deg,#2d465a,#0b1b29 40%,#192d3f); box-shadow:inset 0 0 0 2px #07111b,0 5px 0 #050d16; }
.card::before,.card::after { content:""; position:absolute; width:32px; height:32px; border:3px solid var(--em-accent); pointer-events:none; } .card::before { top:-3px; left:-3px; border-bottom:0; border-right:0; } .card::after { right:-3px; bottom:-3px; border-top:0; border-left:0; }
.header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:8px 8px 12px; border-bottom:1px solid #6a8396; } .ascended-name { margin:0; font:18px var(--em-font-display); } .level { flex:none; color:var(--em-accent); }
.art-fill { height:240px; position:relative; display:flex; align-items:center; justify-content:center; background:radial-gradient(ellipse at 50% 80%,#374d5d,#0b1a26 75%); border:1px solid #58758c; margin-top:10px; }
.portrait { width:100%; height:100%; padding:12px; object-fit:contain; image-rendering:pixelated; } .letter { font:60px var(--em-font-display); color:var(--em-accent); }
.card-meta { display:flex; justify-content:space-between; align-items:center; padding:10px 6px; } .tier { color:var(--tier); } .types { display:flex; gap:6px; }
.stat-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); margin:0; border:1px solid #527088; background:#0b1b28; }
.stat { display:flex; align-items:center; flex-direction:column; padding:10px 4px; } .stat+.stat { border-left:1px solid #527088; } .stat dt { color:var(--em-muted); font-size:11px; text-transform:uppercase; letter-spacing:1px; } .stat dd { margin:0; font:21px var(--em-font-display); } .growth { font-size:10px; color:var(--em-muted); }
.passive { margin:12px 0; padding:10px; border-left:2px solid var(--em-accent); background:#0c1a27; font-size:12px; line-height:1.5; } .passive strong { color:var(--em-accent); }
.ability-list { display:grid; gap:7px; } .ability { display:flex; align-items:center; gap:8px; padding:9px 10px; border:1px solid #617b8d; background:#1b2937; border-left:3px solid var(--em-cat-attack); } .ability.defense { border-left-color:var(--em-cat-defense); } .ability.support { border-left-color:var(--em-cat-support); } .ability.flee { border-left-color:var(--em-cat-flee); } .ability.intercept { border-left-color:var(--em-cat-intercept); }
.ability-text { flex:1; min-width:0; } .ability-text strong { display:block; font-size:12px; } .ability-text span { color:var(--em-muted); font-size:11px; } .unlock { flex:none; font-size:11px; color:var(--em-accent); }
@media(max-width:500px) { .art-fill { height:200px; } .ascended-name { font-size:15px; } }
</style>
