<script setup lang="ts">
import { computed, ref } from "vue";
import type { ActionChoice, BattleView, LegalAction } from "../api/AscensionClient";
import { ROUND_PACE_MS, useAscensionStore } from "../stores/ascension";
import { usePlaybackStore } from "../stores/playback";
import { effectText, titleCase } from "../utils/ascension";
import EmIcon from "./ui/EmIcon.vue";
import EmButton from "./ui/EmButton.vue";
import EmEmblem from "./ui/EmEmblem.vue";
import EmDialog from "./ui/EmDialog.vue";
import EmPanel from "./ui/EmPanel.vue";

/** "Your move": in manual mode one button per legal action, in the colour of its
 * category (the category is also written). Abilities still cooling down are shown
 * disabled with how long. A catch asks which EMBLEM to throw. */
const props = defineProps<{ battle: BattleView }>();
const store = useAscensionStore();
const playback = usePlaybackStore();

const BASIC_LABELS: Record<Exclude<LegalAction["kind"], "ability">, string> = {
  attack: "Attack",
  flee: "Flee",
  catch: "Catch",
};
const BASIC_NOTES: Record<string, string> = { flee: "Try to escape", catch: "Choose an EMBLEM" };
const paceSeconds = ROUND_PACE_MS / 1000;

const locked = computed(() => props.battle.status !== "active" || props.battle.phase !== "choosing" || store.battleBusy || playback.busy);
const coolingDown = computed(() => props.battle.player.abilities.filter((a) => !a.ready));
const ownedTiers = computed(() => (store.catalog?.tiers ?? []).filter((t) => (props.battle.emblems[t.id] ?? 0) > 0));
const catchOpen = ref(false);

function label(action: LegalAction): string {
  if (action.kind === "ability") return action.name ?? titleCase(action.ability_id ?? "ability");
  return BASIC_LABELS[action.kind];
}

function detail(action: LegalAction): string {
  if (action.kind === "flee" || action.kind === "catch") return BASIC_NOTES[action.kind]!;
  const effects = effectText(action.effects);
  return `${titleCase(action.category)} · ${action.percentage}%${effects ? ` · ${effects}` : ""}`;
}

function categoryOf(action: LegalAction): string {
  return action.kind === "flee" ? "flee" : action.kind === "catch" ? "catch" : action.category.toLowerCase();
}

function choose(action: LegalAction): void {
  if (locked.value || props.battle.mode !== "manual") return;
  if (action.kind === "catch") {
    catchOpen.value = true;
    return;
  }
  const choice: ActionChoice =
    action.kind === "ability" && action.ability_id !== null ? { kind: "ability", ability_id: action.ability_id } : { kind: action.kind };
  void store.act(choice);
}

function throwEmblem(tier: string): void {
  catchOpen.value = false;
  void store.act({ kind: "catch", emblem_tier: tier });
}
</script>

<template>
  <EmPanel class="action-bar">
    <div class="head"><EmIcon name="battle" :size="32" />
      <h3>Your move</h3>
      <p class="move-hint">Choose an action for {{ battle.player.name }}.</p>
    </div>

    <p v-if="battle.mode === 'autonomous'" class="muted">Your Ascended chooses on its own, one round every {{ paceSeconds }} seconds.</p>
    <div v-else class="actions">
      <button
        v-for="action in battle.actions"
        :key="`${action.kind}:${action.ability_id ?? ''}`"
        type="button"
        class="action"
        :class="[categoryOf(action), { 'basic-attack': action.kind === 'attack' }]"
        :disabled="locked"
        @click="choose(action)"
      >
        <EmIcon class="action-icon" :name="action.kind === 'catch' ? 'ascended' : action.kind === 'flee' ? 'arrow' : action.category === 'DEFENSE' ? 'shield' : action.category === 'SUPPORT' ? 'flame' : 'sword'" :size="26" />
        <span class="action-name">{{ label(action) }}</span>
        <span class="action-detail">{{ detail(action) }}</span>
      </button>
      <button v-for="ability in coolingDown" :key="`cooldown:${ability.id}`" type="button" class="action" disabled>
        <EmIcon class="action-icon" name="clock" :size="30" /><span class="action-name">{{ ability.name }}</span>
        <span class="action-detail">Cooling down ({{ ability.cooldown }} {{ ability.cooldown === 1 ? "round" : "rounds" }})</span>
      </button>
    </div>

    <EmDialog :open="catchOpen" title="Throw which EMBLEM?" @close="catchOpen = false">
      <p v-if="ownedTiers.length === 0" class="muted none">You have no EMBLEMs. Buy some in the shop.</p>
      <div class="tiers">
        <EmButton v-for="t in ownedTiers" :key="t.id" variant="primary" @click="throwEmblem(t.id)">
          <EmEmblem :tier-id="t.id" :size="28" /> {{ titleCase(t.id) }} ({{ battle.emblems[t.id] }})
        </EmButton>
      </div>
    </EmDialog>
  </EmPanel>
</template>

<style scoped>
.action-bar{display:grid;grid-template-columns:210px minmax(0,1fr);gap:10px;align-items:stretch;padding:8px;border:1px solid var(--em-divider)}.head{display:grid;grid-template-columns:40px 1fr;align-content:center;gap:3px 8px}.head>svg{grid-row:1/3;color:var(--em-accent);align-self:center}.head h3{margin:0;font:17px var(--em-font-display);text-transform:uppercase;color:var(--em-accent)}.move-hint{font-size:11px;color:var(--em-muted)}.actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:6px}.action{display:grid;grid-template-columns:36px minmax(0,1fr);grid-template-rows:auto auto;gap:2px 8px;align-content:center;min-height:78px;padding:9px;border:1px solid var(--em-divider);border-radius:var(--em-radius);color:var(--em-text);background:linear-gradient(140deg,#192f40,#0c1c29);font:inherit;text-align:left;cursor:pointer}.action-icon{grid-row:1/3;align-self:center}.action-name{font-weight:700;font-size:13px}.action-detail{font-size:10px;line-height:1.45;color:var(--em-muted)}.action.basic-attack:not(:disabled){color:var(--em-on-accent);background:linear-gradient(#f7c087,#d98d4e);border-color:var(--em-accent)}.action.basic-attack:not(:disabled) .action-detail{color:var(--em-on-accent)}.action:disabled{opacity:.5;cursor:default}.action:hover:not(:disabled){filter:brightness(1.15)}.action:focus-visible{outline:2px solid var(--em-accent);outline-offset:2px}.tiers{display:flex;flex-wrap:wrap;gap:12px}.none{margin-bottom:12px}.muted{color:var(--em-muted)}
@media(max-width:700px){.action-bar{grid-template-columns:1fr}.head{grid-template-columns:32px 1fr}.head h3{font-size:15px}.actions{grid-template-columns:repeat(2,minmax(0,1fr))}.action{grid-template-columns:26px minmax(0,1fr);gap:2px 5px;padding:7px}.action-name{font-size:12px}.action-icon{max-width:26px}}
</style>
