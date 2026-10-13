<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { abilityEffect, passiveText, titleCase } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
const props = withDefaults(defineProps<{ ascended: AscendedInfo; level?: number; tierId?: string }>(), { level: 1, tierId: "common" });
const tierVar = computed(() => `var(--em-tier-${props.tierId}, var(--em-tier-common))`);
const passiveName = computed(() => titleCase(props.ascended.passive.kind));
const passive = computed(() => passiveText(props.ascended.passive.kind, props.ascended.passive.params));
const stats = computed(() => ([{ key: "hp", label: "HP" }, { key: "power", label: "Power" }, { key: "speed", label: "Speed" }] as const).map(s => ({ ...s, value: props.ascended.base[s.key] ?? 0, growth: props.ascended.growth[s.key] ?? 0 })));
</script>
<template>
  <article class="card" :class="`tier-${tierId}`" :style="{ '--tier': tierVar }" :aria-label="`${ascended.name}, ${titleCase(tierId)}, level ${level}`">
    <AscendedPreviewCard class="template-portrait" :ascended="ascended" :level="level" :tier-id="tierId" show-level />
    <dl class="stat-list"><div v-for="s in stats" :key="s.key" class="stat"><dt>{{ s.label }}</dt><dd>{{ s.value }}</dd><span class="growth">+{{ s.growth }} / lvl</span></div></dl>
    <p class="passive" :title="`${passiveName}: ${passive}`"><strong>{{ passiveName }}</strong><template v-if="passive !== passiveName">{{ ` ${passive}` }}</template></p>
    <div class="ability-list"><div v-for="a in ascended.abilities.slice(0, 3)" :key="a.id" class="ability" :class="a.category.toLowerCase()"><div class="ability-text"><strong>{{ a.name }}</strong><span>{{ abilityEffect(a) }}</span></div><span class="unlock">Lv {{ a.unlock_level }}</span></div></div>
  </article>
</template>
<style scoped>
.card { position:relative; width:var(--card-width,440px); max-width:100%; color:var(--em-text); }
.template-portrait { --card-width:100%; width:100%; max-height:540px; aspect-ratio:.70; }
.stat-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); margin:10px 0 0; border:1px solid #527088; background:#0b1b28; }
.stat { display:flex; align-items:center; flex-direction:column; padding:10px 4px; } .stat+.stat { border-left:1px solid #527088; } .stat dt { color:var(--em-muted); font-size:11px; text-transform:uppercase; letter-spacing:1px; } .stat dd { margin:0; font:21px var(--em-font-display); } .growth { font-size:10px; color:var(--em-muted); }
.passive { margin:12px 0; padding:10px; border-left:2px solid var(--em-accent); background:#0c1a27; font-size:12px; line-height:1.5; } .passive strong { color:var(--em-accent); }
.ability-list { display:grid; gap:7px; } .ability { display:flex; align-items:center; gap:8px; padding:9px 10px; border:1px solid #617b8d; background:#1b2937; border-left:3px solid var(--em-cat-attack); } .ability.defense { border-left-color:var(--em-cat-defense); } .ability.support { border-left-color:var(--em-cat-support); } .ability.flee { border-left-color:var(--em-cat-flee); } .ability.intercept { border-left-color:var(--em-cat-intercept); }
.ability-text { flex:1; min-width:0; } .ability-text strong { display:block; font-size:12px; } .ability-text span { color:var(--em-muted); font-size:11px; } .unlock { flex:none; font-size:11px; color:var(--em-accent); }
</style>
