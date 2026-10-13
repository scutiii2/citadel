<script setup lang="ts">
import { computed, ref } from "vue";
import { useAscensionStore } from "../stores/ascension";
import { ascendedStats } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import HowToPlayDialog from "./HowToPlayDialog.vue";
import EmConfirm from "./ui/EmConfirm.vue";
import EmMenuRow from "./ui/EmMenuRow.vue";
import EmNotice from "./ui/EmNotice.vue";

/** The Ascension main menu, the first screen: the title, the menu rows and a fanned
 * hand of small cards. Without a save it offers New game and previews the starters;
 * with one it offers Quick battle, Collection and Shop and shows your first Ascended.
 * Reset progress lives here, behind a type-to-confirm. */
export type PlayTarget = "collection" | "battle" | "shop";
const emit = defineEmits<{ newGame: []; play: [target: PlayTarget] }>();

const HAND_SIZE = 3;

const store = useAscensionStore();
const hasSave = computed(() => store.profile !== null);
const inBattle = computed(() => store.profile?.active_battle != null || store.battle?.status === "active");
const confirmingReset = ref(false);
const showingHelp = ref(false);

/** The Ascended of the hand: your first ones (level, tier), or the starters to pick from.
 * `rot` and `lift` place a card in the fan, the middle one raised and on top. */
const hand = computed(() => {
  const catalog = store.catalog?.ascendeds ?? [];
  const entries =
    store.profile !== null
      ? store.profile.ascendeds.slice(0, HAND_SIZE).map((s) => ({
          id: s.ascended_id,
          info: catalog.find((c) => c.id === s.ascended_id),
          level: s.level,
          tierId: s.tier_id,
          stars: s.stars,
        }))
      : catalog
          .filter((c) => c.starter)
          .slice(0, HAND_SIZE)
          .map((c) => ({ id: c.id, info: c, level: 1, tierId: c.start_tier, stars: 0 }));
  return entries.flatMap((e, i) => {
    if (e.info === undefined) return [];
    const offset = i - (entries.length - 1) / 2;
    return [{ ...e, info: e.info, stats: ascendedStats(e.info, e.level, store.catalog?.tiers.find((t) => t.id === e.tierId)?.stat_multiplier ?? 1), rot: `${offset * 11}deg`, lift: `${-25 + Math.abs(offset) * 25}px`, z: 10 - Math.round(Math.abs(offset) * 4) }];
  });
});
const handCaption = computed(() => (hasSave.value ? "Your first Ascended" : hand.value.map((h) => h.info.name).join(" · ")));
const ascendedCount = computed(() => store.profile?.ascendeds.length ?? 0);

async function reset(): Promise<void> {
  if (await store.resetProgress()) confirmingReset.value = false;
}
</script>

<template>
  <section class="hero">
    <div class="intro">
      <p class="em-eyebrow">The forge awaits</p>
      <h2 class="em-pixel title">FORGE YOUR<br />LEGEND</h2>
      <p class="tagline">Collect. Forge. Battle.</p>
      <p v-if="hasSave" class="save em-num">{{ ascendedCount }} Ascended, {{ store.profile?.insignia }} Insignia</p>
      <p v-else class="save">Three Ascended. Your first choice.</p>

      <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>

      <nav class="menu" aria-label="Main menu">
        <template v-if="hasSave">
          <EmMenuRow icon="battle" variant="primary" @click="emit('play', 'battle')">Quick battle</EmMenuRow>
          <EmMenuRow icon="ascended" @click="emit('play', 'collection')">Collection</EmMenuRow>
          <EmMenuRow icon="shop" @click="emit('play', 'shop')">Shop</EmMenuRow>
        </template>
        <EmMenuRow v-else icon="play" variant="primary" @click="emit('newGame')">New game</EmMenuRow>
        <EmMenuRow icon="book" @click="showingHelp = true">How to play</EmMenuRow>
        <EmMenuRow class="tavern" icon="lock" disabled><span>Tavern</span> <small>Coming soon / Locked</small></EmMenuRow>
        <EmMenuRow v-if="hasSave" icon="reset" variant="danger" :disabled="inBattle" @click="confirmingReset = true">Reset progress</EmMenuRow>
      </nav>
      <p v-if="hasSave && inBattle" class="caption">Finish or forfeit your battle to reset.</p>
      <p v-else class="caption">{{ hasSave ? "Your progress is ready." : "Pick a starter and begin your collection." }}</p>
    </div>

    <div class="hand-wrap">
      <ul class="hand" :aria-label="hasSave ? 'Your first Ascended' : 'Starter Ascended'">
        <li v-for="ascended in hand" :key="ascended.id" class="ascended" :style="{ '--rot': ascended.rot, '--lift': ascended.lift, zIndex: ascended.z }">
          <AscendedPreviewCard :ascended="ascended.info" :level="ascended.level" :tier-id="ascended.tierId" :stars="ascended.stars" :stats="ascended.stats" show-level />
        </li>
      </ul>
      <p class="hand-caption">{{ handCaption }}</p>
    </div>

    <EmConfirm
      :open="confirmingReset"
      title="Reset all Ascension progress?"
      message="You will start again with a new starter Ascended."
      confirm-label="Reset progress"
      cancel-label="Keep my progress"
      danger
      require-text="RESET"
      :busy="store.busy"
      @confirm="reset"
      @close="confirmingReset = false"
    >
      <EmNotice tone="error" class="reset-notice">This permanently removes your Ascended, Insignia, EMBLEMs and presets.</EmNotice>
    </EmConfirm>

    <HowToPlayDialog :open="showingHelp" @close="showingHelp = false" />
  </section>
</template>

<style scoped>
.hero { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.05fr); align-items:center; gap:36px; min-height:640px; padding:32px; position:relative; isolation:isolate; border:1px solid #3a5c71; background:linear-gradient(90deg,#061622f2 0%,#071725d9 42%,#07172544),var(--em-forge-scene) center / cover; box-shadow:inset 0 0 0 4px #10212e,0 16px 48px #0006; }
.intro { position:relative; z-index:2; min-width:0; }
.title { margin:12px 0; font-size:clamp(32px,4.5vw,64px); line-height:1.12; color:#f6c480; text-shadow:0 3px 0 #835433,0 6px 0 #10151e; }
.tagline { margin-bottom:20px; font-size:23px; font-weight:700; }
.save { border-top:1px solid #4b6c82; padding-top:16px; margin-bottom:24px; color:var(--em-muted); }
.menu { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.menu :deep(.primary) { grid-column:1/-1; min-height:76px; font-size:24px; } .menu :deep(.primary svg) { width:30px; height:30px; }
.menu :deep(.em-row) { padding:16px 12px; } .menu :deep(.em-row.secondary:not(.tavern)) { flex-wrap:wrap; justify-content:center; gap:8px; } .menu :deep(.secondary .label) { flex:initial; font-size:13px; } .menu :deep(.secondary .arrow) { width:14px; }
.menu :deep(.tavern) { grid-column:1/-1; min-height:82px; opacity:.7; } .tavern :deep(.label) { display:flex; flex-direction:column; align-items:flex-start; gap:3px; font-size:20px; } .tavern small { font-size:12px; font-weight:400; }
.menu :deep(.danger) { grid-column:1/-1; margin-top:20px; border:0; border-top:1px solid #496276; background:transparent; box-shadow:none; padding-top:20px; }
.caption { margin-top:14px; font-size:11px; color:var(--em-muted); } .hand-wrap { min-width:0; }
.hand { display:flex; justify-content:center; align-items:center; height:420px; margin:0; padding:0; list-style:none; }
.ascended { --card-width:clamp(145px,16vw,225px); flex:none; margin:0 -18px; transform:rotate(var(--rot)) translateY(var(--lift)); transition:transform 160ms ease; }
.ascended:nth-child(2) :deep(.card) { border-color:var(--em-accent); box-shadow:inset 0 0 0 2px #151719,0 0 0 2px #b97843,0 20px 30px #0008; }
.ascended:hover { z-index:20!important; transform:rotate(0deg) translateY(-30px); } .hand-caption { text-align:center; font:15px var(--em-font-display); color:var(--em-text); margin-top:16px; } .reset-notice { margin-bottom:18px; }
@media(max-width:1000px) { .hero { padding:24px; gap:16px; } .menu :deep(.em-row.secondary:not(.tavern)) { flex-direction:column; } .menu :deep(.secondary .arrow) { display:none; } .ascended { --card-width:150px; margin:0 -28px; } }
@media(max-width:700px) { .hero { grid-template-columns:minmax(0,1fr); padding:24px 16px; min-height:0; } .title { font-size:36px; } .tagline { font-size:18px; } .hand { height:260px; } .ascended { --card-width:clamp(90px,25vw,130px); margin:0 -12px; } .hand-wrap { margin-top:24px; } .menu :deep(.primary) { font-size:20px; min-height:64px; } }
</style>
