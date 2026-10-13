<script setup lang="ts">
import { computed } from "vue";
import type { BattleView, Side } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { spriteFor } from "../utils/sprites";
import { actionTone, describeAction, describeEvent } from "../utils/ascension";
import EmIcon from "./ui/EmIcon.vue";
import EmPanel from "./ui/EmPanel.vue";

/** The battle's revealed rounds in words, latest first. Each round is a block with a sticky
 * "Round N" heading, one colour-coded pick per side, then what happened. It is a polite live
 * region and does not scroll by itself. */
const props = defineProps<{ battle: BattleView }>();
const store = useAscensionStore();
const portrait = (side: Side) => spriteFor(store.catalog?.ascendeds.find(a => a.id === props.battle[side].ascended_id)?.art, "battle");
const names = computed(() => ({ player: props.battle.player.name, wild: props.battle.wild.name }));
const rounds = computed(() => [...props.battle.history].reverse());
const SIDES: readonly Side[] = ["player", "wild"];

function pick(side: Side, entry: BattleView["history"][number]) {
  const [key, category] = entry.actions[side];
  const fighter = side === "player" ? props.battle.player : props.battle.wild;
  return { side, who: names.value[side], move: describeAction(key, fighter.abilities), tone: actionTone(key, category) };
}
</script>

<template>
  <EmPanel class="round-log">
    <div class="head">
      <h3><EmIcon name="battle" /> Battle log</h3>
      <span id="battle-log-controls" />
    </div>
    <p v-if="battle.history.length === 0" class="empty">No rounds yet.</p>
    <ol v-else class="rounds" aria-live="polite">
      <li v-for="(entry, index) in rounds" :key="entry.round" class="round" :class="{ latest: index === 0 }">
        <div class="round-head">
          <h4 class="title"><span class="label">Round</span> <span class="num em-num">{{ entry.round }}</span></h4>
          <span v-if="index === 0" class="now">Latest</span>
        </div>
        <ul class="picks">
          <li v-for="side in SIDES" :key="side" class="pick" :class="side">
            <img v-if="portrait(side)" class="log-portrait" :src="portrait(side)!" alt="" />
            <span class="who">{{ pick(side, entry).who }}</span>
            <span class="move" :class="`tone-${pick(side, entry).tone}`">{{ pick(side, entry).move }}</span>
          </li>
        </ul>
        <ul class="events">
          <li v-for="(event, eventIndex) in entry.events" :key="eventIndex" class="event">{{ describeEvent(event, names) }}</li>
        </ul>
      </li>
    </ol>
  </EmPanel>
</template>

<style scoped>
.round-log{min-width:0;height:100%;padding:9px;display:flex;flex-direction:column}.head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-bottom:9px;margin-bottom:9px;border-bottom:1px solid var(--em-divider)}.head h3{display:flex;align-items:center;gap:7px;margin:0;font:15px var(--em-font-display);text-transform:uppercase}.head :deep(.em-button){font-size:11px;min-height:30px;padding:4px 8px}.rounds{display:grid;gap:8px;max-height:390px;margin:0;padding:0 3px 0 0;overflow-y:auto;list-style:none}.round{border:1px solid var(--em-divider);background:linear-gradient(130deg,#142838,#091c29)}.round-head{display:flex;justify-content:space-between;align-items:center;padding:5px 8px}.title{margin:0;display:flex;gap:5px;font-size:11px}.now{font-size:10px;color:var(--em-accent)}.picks,.events{margin:0;padding:0;list-style:none}.picks{display:grid;gap:5px;padding:5px 8px}.pick{display:grid;grid-template-columns:36px minmax(0,1fr);gap:1px 7px;align-items:center}.log-portrait{width:36px;height:42px;object-fit:contain;grid-row:1/3;background:#071019;image-rendering:pixelated}.who,.move{font-size:11px}.who{color:var(--em-muted)}.move{font-weight:700}.tone-attack{color:var(--em-cat-attack)}.tone-defense{color:var(--em-cat-defense)}.tone-support{color:var(--em-cat-support)}.tone-flee{color:var(--em-cat-flee)}.tone-catch{color:var(--em-cat-intercept)}.event{padding:5px 8px;border-top:1px solid var(--em-divider);font-size:11px;line-height:1.5}.empty{color:var(--em-muted);font-size:12px}
@media(max-width:900px){.rounds{max-height:245px}}
</style>