<script setup lang="ts">
import { computed, ref } from "vue";
import type { BattleView, ResultKind } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { RESULT_LABELS, formatCountdown, titleCase } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import EmButton from "./ui/EmButton.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmPanel from "./ui/EmPanel.vue";
import type { IconName } from "./ui/icons";

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

const TONES: Record<ResultKind, { tone: "success" | "danger" | "accent" | "warning"; icon: IconName }> = {
  won: { tone: "success", icon: "shield" },
  knocked_out: { tone: "danger", icon: "heart" },
  captured: { tone: "accent", icon: "ascended" },
  escaped: { tone: "warning", icon: "arrow" },
  wild_escaped: { tone: "warning", icon: "arrow" },
  forfeited: { tone: "danger", icon: "battle" },
};

const style = computed(() => (result.value ? TONES[result.value.kind] : TONES.won));
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
    <div class="mark" :class="style.tone" aria-hidden="true"><EmIcon :name="style.icon" :size="40" /></div>
    <h2 class="em-pixel title">{{ RESULT_LABELS[result.kind] }}</h2>
    <p class="story">{{ story }}</p>
    <img v-if="featuredArt && !imageFailed" class="result-art" :src="featuredArt" alt="" draggable="false" @error="imageFailed = true" />
    <span v-else class="result-letter em-pixel" aria-hidden="true">{{ featured.name.slice(0, 1) }}</span>
    </div>

    <div v-if="awarded" class="rewards">
      <h3 class="rewards-heading em-pixel">Rewards</h3>
      <div v-if="result.xp !== undefined" class="reward">
        <strong class="em-pixel em-num">+{{ result.xp }} XP</strong>
        <span>for {{ battle.player.name }}<template v-if="levelledUp">, now level {{ result.level_after }}</template></span>

      </div>
      <div v-if="result.insignia !== undefined" class="reward">
        <strong class="em-pixel em-num">+{{ result.insignia }} Insignia</strong>
        <span>added to your wallet</span>
      </div>
      <div v-if="result.essence !== undefined && result.essence_tier_id" class="reward">
        <strong class="em-pixel em-num">+{{ result.essence }} {{ titleCase(result.essence_tier_id) }} essence</strong>
        <span>for upgrading stars</span>
      </div>
      <div v-if="result.copies_granted !== undefined" class="reward">
        <strong class="em-pixel em-num">+{{ result.copies_granted }} {{ result.copies_granted === 1 ? "copy" : "copies" }}</strong>
        <span>of {{ battle.wild.name }}<template v-if="result.tier_id">, at {{ titleCase(result.tier_id) }}</template></span>
      </div>
    </div>
    <p v-else class="none">No rewards from this battle.</p>

    <div class="result-details">
        <div v-if="result.squad_xp?.length" class="squad-xp">
          <h3>Squad XP</h3>
          <ul>
            <li v-for="member in result.squad_xp" :key="member.ascended_id">
              +{{ member.xp }} XP · {{ member.name }}<template v-if="member.level_after > member.level_before">, now level {{ member.level_after }}</template>
            </li>
          </ul>
        </div>
    <template v-if="result.revealed_personalities?.length">
      <h3 class="revealed-title">Personalities revealed</h3>
      <ul class="revealed">
        <li v-for="p in result.revealed_personalities" :key="p.id">
          {{ titleCase(p.type) }} · tier {{ p.tier }}<strong v-if="p.id === result.awarded_personality?.id"> (now yours)</strong>
        </li>
      </ul>
    </template>

    <EmButton variant="primary" @click="store.closeBattle()">Back</EmButton>
    </div>
  </EmPanel>
</template>

<style scoped>
.battle-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 760px;
  margin: 0 auto var(--em-space-5);
  text-align: center;
  background:
    radial-gradient(ellipse at top, #3c352c, transparent 70%),
    var(--em-panel);
}
.mark {
  display: grid;
  width: 80px;
  height: 80px;
  place-items: center;
  margin-bottom: var(--em-space-4);
  border: 1px solid currentColor;
  background: #15202b;
  clip-path: polygon(12% 0, 88% 0, 100% 12%, 100% 88%, 88% 100%, 12% 100%, 0 88%, 0 12%);
}
.mark.success {
  color: var(--em-success);
}
.mark.danger {
  color: var(--em-danger);
}
.mark.accent {
  color: var(--em-accent);
}
.mark.warning {
  color: var(--em-warning);
}
.title {
  margin: 0 0 var(--em-space-2);
  font-size: 28px;
  line-height: 1.3;
}
.story {
  max-width: 480px;
  color: var(--em-muted);
}
.rewards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--em-space-4);
  width: 100%;
  margin: var(--em-space-5) 0;
}
.reward {
  padding: var(--em-space-4);
  border: 1px solid var(--em-border);
  background: #15202b;
}
.reward strong {
  display: block;
  margin-bottom: 5px;
  font-size: 22px;
  font-weight: 400;
  color: var(--em-accent);
}
.reward span {
  font-size: 13px;
  color: var(--em-muted);
}
.squad-xp {
  margin-top: var(--em-space-3);
  padding-top: var(--em-space-3);
  border-top: 1px solid var(--em-border);
  text-align: left;
  font-size: 13px;
  color: var(--em-muted);
}
.squad-xp h3 {
  margin: 0 0 var(--em-space-2);
  font-size: 14px;
  color: var(--em-text);
}
.squad-xp ul {
  padding: 0;
  margin: 0;
  list-style: none;
}
.none {
  margin: var(--em-space-5) 0;
  padding: 14px;
  border: 1px dashed var(--em-border);
  color: var(--em-muted);
  font-size: 13px;
}
.revealed-title {
  margin: 0 0 var(--em-space-2);
  font-size: 16px;
}
.revealed {
  margin: 0 0 var(--em-space-5);
  padding: 0;
  list-style: none;
  color: var(--em-muted);
}
@media (max-width: 700px) {
  .title {
    font-size: 23px;
  }
  .reward strong {
    font-size: 20px;
  }
}

.battle-result { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, .75fr) minmax(0, 1fr); gap: 10px; max-width: none; width: 100%; padding: 10px; align-items: stretch; text-align: left; background: var(--em-header); }
.result-scene { display: flex; flex-direction: column; align-items: center; min-width: 0; padding: 20px 12px 10px; text-align: center; border: 1px solid var(--em-divider); background: linear-gradient(180deg, #07121ecc, #10172055), var(--em-forge-scene, radial-gradient(ellipse at bottom, #54402a, #101720)); background-position: center; background-size: cover; }
.mark { width: 44px; height: 44px; margin-bottom: 8px; }
.mark :deep(svg) { width: 28px; height: 28px; }
.title { font-size: 24px; color: var(--em-accent); }
.story { font-size: 13px; line-height: 1.5; }
.result-art { display: block; width: 100%; height: 230px; object-fit: contain; margin-top: 10px; image-rendering: pixelated; mix-blend-mode: lighten; }
.result-letter { display: grid; place-items: center; height: 230px; font-size: 80px; color: var(--em-muted); }
.rewards { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 10px; border: 1px solid var(--em-divider); }
.rewards-heading { margin: 0 0 4px; font-size: 14px; text-transform: uppercase; }
.reward { padding: 12px; background: linear-gradient(140deg, var(--em-raised), var(--em-header)); border-color: var(--em-divider); }
.reward strong { font-family: var(--em-font-body); font-size: 16px; font-weight: 700; }
.reward span { font-size: 11px; }
.result-details { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 12px; border: 1px solid var(--em-divider); background: linear-gradient(145deg, var(--em-panel), var(--em-header)); }
.squad-xp { margin: 0; padding: 0; border: 0; }
.squad-xp h3, .revealed-title { font-family: var(--em-font-display); text-transform: uppercase; font-size: 13px; }
.squad-xp li, .revealed li { padding: 8px; margin-top: 6px; border: 1px solid var(--em-divider); background: var(--em-header); font-size: 12px; }
.revealed { margin: 0; }
.result-details :deep(.em-button) { width: 100%; margin-top: auto; }
.none { margin: 0; align-self: start; }
@media (max-width: 950px) { .battle-result { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } .result-details { grid-column: 1 / -1; } }
@media (max-width: 600px) { .battle-result { grid-template-columns: minmax(0, 1fr); } .result-details { grid-column: 1; } .title { font-size: 22px; } .result-art { height: 190px; } }
</style>
