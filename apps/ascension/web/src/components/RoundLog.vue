<script setup lang="ts">
import { computed } from "vue";
import type { BattleView, Side } from "../api/AscensionClient";
import { actionTone, describeAction, describeEvent } from "../utils/ascension";
import EmIcon from "./ui/EmIcon.vue";
import EmPanel from "./ui/EmPanel.vue";

/** The battle's revealed rounds in words, latest first. Each round is a block with a sticky
 * "Round N" heading, one colour-coded pick per side, then what happened. It is a polite live
 * region and does not scroll by itself. */
const props = defineProps<{ battle: BattleView }>();
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
      <h3>Round log</h3>
      <small>Latest first <EmIcon name="arrow" :size="14" class="down" /></small>
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
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--em-space-3);
  margin-bottom: var(--em-space-4);
}
.head h3 {
  margin: 0;
  font-size: 18px;
}
.head small {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--em-muted);
}
.down {
  transform: rotate(90deg);
}
.empty {
  color: var(--em-muted);
}
.rounds {
  display: grid;
  gap: var(--em-space-3);
  max-height: 320px;
  margin: 0;
  padding: 0 var(--em-space-2) 0 0;
  overflow-y: auto;
  list-style: none;
}
.round {
  border: 1px solid var(--em-divider);
  border-left: 3px solid var(--em-divider);
  background: var(--em-raised);
}
.round.latest {
  border-color: var(--em-accent-edge);
  border-left-color: var(--em-accent);
}
.round-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-3);
  padding: 6px var(--em-space-3);
  background: var(--em-header);
  border-bottom: 1px solid var(--em-divider);
}
.title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  font-family: var(--em-font-display);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.title .num {
  font-size: 18px;
  color: var(--em-accent);
}
.latest .title .label {
  color: var(--em-text);
}
.title .label {
  color: var(--em-muted);
}
.now {
  padding: 1px 8px;
  border: 1px solid var(--em-accent-edge);
  font-size: 11px;
  color: var(--em-accent);
}
.picks,
.events {
  margin: 0;
  padding: 0;
  list-style: none;
}
.picks {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--em-space-2);
  padding: var(--em-space-2) var(--em-space-3);
}
.pick {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.who {
  overflow: hidden;
  font-size: 12px;
  color: var(--em-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.move {
  font-size: 15px;
  font-weight: 700;
}
.tone-attack {
  color: var(--em-cat-attack);
}
.tone-defense {
  color: var(--em-cat-defense);
}
.tone-support {
  color: var(--em-cat-support);
}
.tone-flee {
  color: var(--em-cat-flee);
}
.tone-catch {
  color: var(--em-cat-intercept);
}
.tone-other {
  color: var(--em-text);
}
.event {
  padding: 6px var(--em-space-3);
  border-top: 1px solid var(--em-divider);
  font-size: 13px;
}
</style>
