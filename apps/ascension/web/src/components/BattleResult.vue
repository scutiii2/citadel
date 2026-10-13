<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { BattleView } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { RESULT_LABELS, formatCountdown, titleCase } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import EmButton from "./ui/EmButton.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmPanel from "./ui/EmPanel.vue";
import EmBar from "./ui/EmBar.vue";
import EmEmblem from "./ui/EmEmblem.vue";


/** A finished battle: one banner per outcome (the outcome is always written), what it
 * paid (only what was awarded), the personalities a capture revealed, and Back to the
 * encounter screen. */
const props = defineProps<{ battle: BattleView }>();
const store = useAscensionStore();
const now = useNowSeconds();
const result = computed(() => props.battle.result);
const imageFailed = ref(false);
const featured = computed(() => result.value?.kind === "captured" ? props.battle.wild : props.battle.player);
const featuredArt = computed(() => spriteFor(store.catalog?.ascendeds.find(a => a.id === featured.value.ascended_id)?.art, "battle"));

const squadRewards = computed(() => [...(result.value?.xp !== undefined ? [{ ascended_id: props.battle.player.ascended_id, name: props.battle.player.name, xp: result.value.xp, level_before: result.value.level_before ?? props.battle.player.level, level_after: result.value.level_after ?? props.battle.player.level }] : []), ...(result.value?.squad_xp ?? [])]);
const memberProgress = (id: string) => store.profile?.ascendeds.find(a => a.ascended_id === id);
const memberArt = (id: string) => spriteFor(store.catalog?.ascendeds.find(a => a.id === id)?.art, "battle");


const revealed = computed(() => result.value?.revealed_personalities ?? []);
const awardedIndex = computed(() => revealed.value.findIndex(p => p.id === result.value?.awarded_personality?.id));
const LAPS = 3;
const lit = ref<number | null>(null);
const settled = ref(!(revealed.value.length > 1 && awardedIndex.value >= 0));
let spinTimer: ReturnType<typeof setTimeout> | undefined;

/** Suspense roulette: the highlight laps the revealed cards, slowing down, and stops on the awarded one. */
function spin() {
  const count = revealed.value.length;
  const stop = LAPS * count + awardedIndex.value;
  let step = 0;
  const tick = () => {
    lit.value = step % count;
    if (step === stop) { spinTimer = setTimeout(settle, 450); return; }
    spinTimer = setTimeout(tick, 100 + step * step * 3.5);
    step += 1;
  };
  tick();
}
function settle() {
  clearTimeout(spinTimer);
  lit.value = null;
  settled.value = true;
}
onMounted(() => {
  if (!settled.value) spin();
});
onBeforeUnmount(() => clearTimeout(spinTimer));

const restLeft = computed(() => {
  const until = result.value?.faint_until;
  return until === undefined ? 0 : Math.max(0, until - now.value);
});
const levelledUp = computed(() => {
  const r = result.value;
  return r?.level_before !== undefined && r.level_after !== undefined && r.level_after > r.level_before;
});
const awarded = computed(() => {
  const r = result.value;
  return r !== null && (r.xp !== undefined || r.insignia !== undefined || r.essence !== undefined || r.copies_granted !== undefined);
});
const story = computed(() => {
  const r = result.value;
  if (r === null) return "";
  const rest = restLeft.value > 0 ? ` Ready again in ${formatCountdown(restLeft.value)}.` : "";
  const mine = props.battle.player.name;
  const theirs = props.battle.wild.name;
  switch (r.kind) {
    case "won":
      return `${mine} stood its ground. A well-earned victory.`;
    case "knocked_out":
      return `${mine} fainted and needs rest before its next battle.${rest}`;
    case "captured":
      return `A wild ${theirs} joins your collection.`;
    case "escaped":
      return `You slipped away safely. ${mine} lives to fight again.`;
    case "wild_escaped":
      return `The wild ${theirs} got away this time.`;
    case "forfeited":
      return `${mine} fainted and needs rest before its next battle.${rest}`;
  }
});
</script>

<template>
  <EmPanel v-if="result" class="battle-result" role="status">
    <div class="result-scene">
    <div class="result-title"><EmEmblem tier-id="common" :size="36" /><h2 class="em-pixel title">{{ RESULT_LABELS[result.kind] }}</h2><EmEmblem tier-id="common" :size="36" /></div>
    <p class="story">{{ story }}</p>
    <img v-if="featuredArt && !imageFailed" class="result-art" :src="featuredArt" alt="" draggable="false" @error="imageFailed = true" />
    <span v-else class="result-letter em-pixel" aria-hidden="true">{{ featured.name.slice(0, 1) }}</span>
    </div>

    <div class="rewards">
      <h3 class="rewards-heading em-pixel"><EmIcon name="shop" /> Rewards</h3>
      <p v-if="!awarded" class="none">No rewards from this battle.</p>
      <div v-if="result.xp !== undefined" class="reward"><EmIcon class="reward-icon" name="ascended" :size="34" />
        <strong class="em-pixel em-num">+{{ result.xp }} XP</strong>
        <span>for {{ battle.player.name }}<template v-if="levelledUp">, now level {{ result.level_after }}</template></span>

      </div>
      <div v-if="result.insignia !== undefined" class="reward"><EmEmblem class="reward-icon" tier-id="common" :size="34" />
        <strong class="em-pixel em-num">+{{ result.insignia }} Insignia</strong>
        <span>added to your wallet</span>
      </div>
      <div v-if="result.essence !== undefined && result.essence_tier_id" class="reward"><EmIcon class="reward-icon" name="flame" :size="34" />
        <strong class="em-pixel em-num">+{{ result.essence }} {{ titleCase(result.essence_tier_id) }} essence</strong>
        <span>for upgrading stars</span>
      </div>
      <div v-if="result.copies_granted !== undefined" class="reward"><img v-if="memberArt(battle.wild.ascended_id)" class="reward-icon copy-icon" :src="memberArt(battle.wild.ascended_id)!" alt="" />
        <strong class="em-pixel em-num">+{{ result.copies_granted }} {{ result.copies_granted === 1 ? "copy" : "copies" }}</strong>
        <span>of {{ battle.wild.name }}<template v-if="result.tier_id">, at {{ titleCase(result.tier_id) }}</template></span>
      </div>
    </div>


    <div class="result-details">
        <div v-if="squadRewards.length" class="squad-xp">
          <h3><EmIcon name="ascended" /> Squad XP</h3>
          <ul>
            <li v-for="member in squadRewards" :key="member.ascended_id">
              <img v-if="memberArt(member.ascended_id)" :src="memberArt(member.ascended_id)!" alt="" /><div class="xp-copy">+{{ member.xp }} XP · {{ member.name }}<template v-if="member.level_after > member.level_before">, now level {{ member.level_after }}</template><EmBar v-if="memberProgress(member.ascended_id)" :value="memberProgress(member.ascended_id)!.xp" :max="memberProgress(member.ascended_id)!.xp_needed ?? memberProgress(member.ascended_id)!.xp" :label="`${member.name} experience`" /></div>
            </li>
          </ul>
        </div>
    <template v-if="result.revealed_personalities?.length">
      <h3 class="revealed-title">Personalities revealed</h3>
      <ul class="revealed" :title="settled ? undefined : 'Click to skip'" @click="settled || settle()">
        <li v-for="(p, i) in revealed" :key="p.id" :class="{ lit: lit === i, won: settled && p.id === result.awarded_personality?.id, dim: settled && result.awarded_personality && p.id !== result.awarded_personality.id && revealed.length > 1 }">
          {{ titleCase(p.type) }} · tier {{ p.tier }}<strong v-if="settled && p.id === result.awarded_personality?.id"> (now yours)</strong>
        </li>
      </ul>
    </template>

    <EmButton variant="primary" @click="store.closeBattle()"><EmIcon name="arrow" class="back-arrow" /> Back to encounters</EmButton>
    </div>
  </EmPanel>
</template>

<style scoped>
.battle-result{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,.72fr) minmax(0,1fr);gap:8px;padding:0;border:0;background:transparent;box-shadow:none;align-items:stretch}.result-scene{position:relative;display:flex;flex-direction:column;align-items:center;min-width:0;padding:18px 12px 8px;text-align:center;border:1px solid var(--em-divider);background:var(--em-result-scene,var(--em-battle-scene,var(--em-forge-scene))) center / cover;min-height:370px}.result-title{display:flex;align-items:center;justify-content:center;gap:10px}.title{margin:0;font-size:32px;color:var(--em-accent);text-shadow:0 3px #352013;text-transform:uppercase}.story{font-weight:700;font-size:14px;text-shadow:0 2px #000;margin-top:6px}.result-art{display:block;width:90%;height:265px;object-fit:contain;margin-top:auto;image-rendering:pixelated;mix-blend-mode:lighten}.result-letter{display:grid;place-items:center;height:265px;font:80px var(--em-font-display);color:var(--em-muted)}.rewards{display:flex;flex-direction:column;gap:8px;padding:10px;border:1px solid var(--em-divider);background:#0c1d2a}.rewards-heading,.squad-xp h3,.revealed-title{display:flex;align-items:center;gap:8px;margin:0 0 3px;font:15px var(--em-font-display);text-transform:uppercase}.reward{position:relative;padding:12px 10px 12px 50px;border:1px solid var(--em-divider);background:linear-gradient(140deg,#193345,#0e2231);min-height:68px;display:flex;flex-direction:column;justify-content:center}.reward-icon{position:absolute;left:8px;top:50%;transform:translateY(-50%);color:var(--em-accent)}.copy-icon{width:34px;height:44px;object-fit:contain;image-rendering:pixelated}.reward strong{display:block;font:700 16px var(--em-font-body);color:var(--em-text);margin-bottom:4px}.reward span{font-size:11px;color:var(--em-muted)}.none{font-size:12px;color:var(--em-muted);padding:10px}.result-details{display:flex;flex-direction:column;gap:10px;min-width:0;padding:10px;border:1px solid var(--em-divider);background:#0c1d2a}.squad-xp ul,.revealed{padding:0;margin:0;list-style:none}.squad-xp li{display:flex;align-items:center;gap:8px;padding:6px;border:1px solid var(--em-divider);background:#102634;margin-top:5px;font-size:12px}.squad-xp img{width:38px;height:44px;object-fit:contain;background:#071019;image-rendering:pixelated}.xp-copy{flex:1;min-width:0}.xp-copy :deep(.em-bar){margin-top:5px}.revealed{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.revealed li{padding:12px 8px;border:1px solid var(--em-divider);background:#102634;font-size:12px;color:var(--em-muted);transition:opacity .3s,border-color .15s,box-shadow .15s,background .15s}.revealed li.lit{border-color:var(--em-accent);background:#1d3a4d;color:var(--em-text);box-shadow:0 0 10px var(--em-accent)}.revealed li.won{border-color:var(--em-accent);color:var(--em-text);box-shadow:0 0 14px var(--em-accent)}.revealed li.dim{opacity:.45}.result-details :deep(.em-button){margin-top:auto;width:100%}.back-arrow{transform:scaleX(-1)}
@media(max-width:950px){.battle-result{grid-template-columns:1fr 1fr}.result-details{grid-column:1/-1}.title{font-size:25px}}@media(max-width:600px){.battle-result{grid-template-columns:1fr}.result-details{grid-column:1}.result-scene{min-height:350px}.title{font-size:28px}}
</style>