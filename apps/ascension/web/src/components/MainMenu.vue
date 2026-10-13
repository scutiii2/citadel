<script setup lang="ts">
import { computed, ref } from "vue";
import { useAscensionStore } from "../stores/ascension";
import { ascendedStats } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import HowToPlayDialog from "./HowToPlayDialog.vue";
import EmConfirm from "./ui/EmConfirm.vue";
import EmMenuRow from "./ui/EmMenuRow.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmEmblem from "./ui/EmEmblem.vue";

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
  const arranged = entries.length === HAND_SIZE ? [entries[2]!, entries[0]!, entries[1]!] : entries;
  return arranged.flatMap((e, i) => {
    if (e.info === undefined) return [];
    const offset = i - (entries.length - 1) / 2;
    return [{ ...e, info: e.info, stats: ascendedStats(e.info, e.level, store.catalog?.tiers.find(t => t.id === e.tierId)?.stat_multiplier ?? 1), rot: `${offset * 11}deg`, lift: `${-25 + Math.abs(offset) * 25}px`, z: 10 - Math.round(Math.abs(offset) * 4) }];
  });
});
const handCaption = computed(() => (hasSave.value ? "Your Ascended" : hand.value.map((h) => h.info.name).join(" · ")));
const ascendedCount = computed(() => store.profile?.ascendeds.length ?? 0);

async function reset(): Promise<void> {
  if (await store.resetProgress()) confirmingReset.value = false;
}
</script>

<template>
  <section class="hero">
    <div class="intro">
      <h2 class="em-pixel title">FORGE YOUR<br />LEGEND</h2>
      <p class="tagline">Collect. Forge. Battle.</p>
      <p v-if="hasSave" class="save"><EmEmblem tier-id="common" :size="40" /><strong>{{ ascendedCount }} Ascended</strong> <span>· Progress saved</span></p>
      <p v-else class="save">Three Ascended. Your first choice.</p>

      <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>

      <nav class="menu" aria-label="Main menu">
        <template v-if="hasSave">
          <EmMenuRow icon="battle" variant="primary" @click="emit('play', 'battle')">Quick battle</EmMenuRow>
          <EmMenuRow icon="ascended" @click="emit('play', 'collection')"><template #icon><svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><path d="M3 8l10-3 6 21-10 3zM13 4h11v22M22 6l8 3-5 19" fill="none" stroke="currentColor" stroke-width="2" /></svg></template>Collection</EmMenuRow>
          <EmMenuRow icon="shop" @click="emit('play', 'shop')">Shop</EmMenuRow>
        </template>
        <EmMenuRow v-else icon="play" variant="primary" @click="emit('newGame')">New game</EmMenuRow>
        <EmMenuRow icon="book" @click="showingHelp = true">How to play</EmMenuRow>
        <EmMenuRow class="tavern" icon="lock" disabled :show-arrow="false">
          <template #icon><svg class="tankard" width="48" height="48" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 9h16v18H6zM8 5h12v4H8zM22 12h6v11h-6M5 28h18M9 13v9M13 13v9M17 13v9" fill="none" stroke="currentColor" stroke-width="3" /></svg></template>
          <span>Tavern</span> <small>Hire Ascended · Coming soon</small>
          <template #trailing><span class="locked-state"><EmIcon name="lock" :size="28" />LOCKED</span></template>
        </EmMenuRow>
        <EmMenuRow v-if="hasSave" icon="reset" variant="danger" :show-arrow="false" :disabled="inBattle" @click="confirmingReset = true">Reset progress</EmMenuRow>
      </nav>
      <p v-if="hasSave && inBattle" class="caption">Finish or forfeit your battle to reset.</p>

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
.hero { display:grid; grid-template-columns:minmax(0,41%) minmax(0,59%); align-items:center; min-height:760px; padding:20px 20px 64px; position:relative; isolation:isolate; background:linear-gradient(90deg,#041420ef 0%,#041420d9 36%,#0414200d 65%),var(--em-menu-scene,var(--em-forge-scene)) center / cover; }
.intro { position:relative; z-index:2; min-width:0; align-self:start; }
.title { margin:0 0 4px; font-size:clamp(36px,4.7vw,74px); line-height:1.05; letter-spacing:-.035em; color:#ffcf83; text-shadow:0 3px 0 #a76234,0 5px 0 #141a20; }
.tagline { margin:0 0 14px; font-family:var(--em-font-display); font-size:clamp(17px,2vw,30px); font-weight:700; }
.save { display:flex; align-items:center; gap:12px; border-top:1px solid #597c91; padding-top:16px; margin:0 0 28px; color:#bdd7e9; font-size:clamp(13px,1.35vw,21px); }
.save strong { color:#f1f1ec; white-space:nowrap; } .save img { width:40px; height:40px; object-fit:contain; image-rendering:pixelated; }
.menu { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.menu :deep(.primary) { grid-column:1/-1; min-height:74px; font-size:clamp(22px,2.1vw,34px); padding:10px 20px; } .menu :deep(.primary .label) { text-align:center; } .menu :deep(.primary svg) { width:40px; height:40px; }
.menu :deep(.secondary:not(.tavern)) { min-height:94px; padding:12px 10px; gap:8px; } .menu :deep(.secondary:not(.tavern) .label) { font-size:clamp(12px,1.2vw,19px); white-space:nowrap; } .menu :deep(.secondary:not(.tavern) svg:first-child) { width:32px; height:32px; color:#efb96f; } .menu :deep(.secondary .arrow) { width:13px; }
.menu :deep(.tavern) { grid-column:1/-1; min-height:98px; margin-top:6px; padding:14px 24px; gap:24px; border-color:#667e8c; color:#94a4af; background:#0c1d27c9; } .tavern :deep(.label) { display:flex; flex-direction:column; align-items:flex-start; gap:6px; font:700 26px var(--em-font-display); } .tavern small { font:400 clamp(12px,1.25vw,20px) var(--em-font-body); } .locked-state { display:flex; flex-direction:column; align-items:center; gap:5px; font-size:12px; }
.menu :deep(.danger) { grid-column:1/-1; margin-top:22px; border:0; border-top:1px solid #496276; border-radius:0; background:transparent; box-shadow:none; padding:24px 10px 0; font-size:18px; font-weight:400; }
.caption { margin-top:14px; font-size:12px; color:var(--em-muted); } .hand-wrap { min-width:0; padding-top:110px; }
.hand { display:flex; justify-content:center; align-items:center; height:440px; margin:0; padding:0; list-style:none; }
.ascended { --card-width:clamp(175px,18.5vw,290px); flex:none; margin:0 -15px; transform:rotate(var(--rot)) translateY(var(--lift)); transition:transform 160ms ease; }
.ascended:nth-child(2) { --card-width:clamp(190px,19.5vw,310px); }
.ascended:hover { z-index:20!important; transform:rotate(0deg) translateY(-30px); } .hand-caption { display:flex; align-items:center; justify-content:center; gap:20px; text-align:center; font:700 20px var(--em-font-display); color:var(--em-text); margin:22px 0 0; } .hand-caption::before,.hand-caption::after { content:""; width:75px; height:2px; background:linear-gradient(90deg,transparent,#f6b557,transparent); } .reset-notice { margin-bottom:18px; }
@media(max-width:1100px) { .hero { padding:20px 14px 42px; min-height:660px; } .title { font-size:4.7vw; } .save { gap:8px; font-size:13px; } .save img { width:30px; height:30px; } .menu { gap:8px; } .menu :deep(.secondary:not(.tavern)) { padding:10px 5px; gap:5px; } .menu :deep(.secondary:not(.tavern) svg:first-child) { width:25px; height:25px; } .menu :deep(.secondary:not(.tavern) .label) { font-size:12px; } .menu :deep(.secondary .arrow) { width:9px; } .hand { height:360px; } .ascended { --card-width:19vw; margin:0 -12px; } .ascended:nth-child(2) { --card-width:20vw; } .hand-caption { font-size:16px; } .tavern :deep(.label) { font-size:20px; } .menu :deep(.tavern) { padding:12px; gap:12px; } }
@media(max-width:700px) { .hero { grid-template-columns:minmax(0,1fr); padding:18px 14px 30px; min-height:0; background-position:60% center; } .title { font-size:clamp(36px,9vw,60px); } .tagline { font-size:18px; } .save { margin-bottom:24px; } .hand { height:320px; } .ascended { --card-width:31vw; margin:0 -10px; } .ascended:nth-child(2) { --card-width:34vw; } .hand-wrap { padding-top:26px; } .menu :deep(.primary) { font-size:24px; min-height:68px; } .menu :deep(.secondary:not(.tavern)) { min-height:78px; } .menu :deep(.secondary:not(.tavern) svg:first-child) { width:23px; height:23px; } .menu :deep(.secondary:not(.tavern) .label) { font-size:11px; } .menu :deep(.tavern) { min-height:90px; } .menu :deep(.danger) { margin-top:16px; padding-top:18px; } }
</style>
