<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAscensionClient, type LoadoutSlot, type OwnedAscended, type TreeNodeState, type TreeView } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { passiveText, titleCase } from "../utils/ascension";
import EmButton from "./ui/EmButton.vue";
import EmNotice from "./ui/EmNotice.vue";

/** One Ascended's ability tree: nodes at their own places, learn a node, equip it in a slot. */
const props = defineProps<{ ascended: OwnedAscended }>();
const store = useAscensionStore();
const client = useAscensionClient();

const NODE_W = 124;
const NODE_H = 52;
const ABILITY_SLOTS: LoadoutSlot[] = ["a1", "a2", "a3"];

const tree = ref<TreeView | null>(null);
const selectedId = ref<string | null>(null);
const error = ref("");
/** A failed load, else the failure of the last learn or equip (the store keeps it). */
const shownError = computed(() => error.value || store.error);

const selected = computed(() => tree.value?.nodes.find((n) => n.id === selectedId.value) ?? null);
const byId = computed(() => new Map((tree.value?.nodes ?? []).map((n) => [n.id, n])));
const width = computed(() => Math.max(300, ...(tree.value?.nodes ?? []).map((n) => n.x + NODE_W + 24)));
const height = computed(() => Math.max(200, ...(tree.value?.nodes ?? []).map((n) => n.y + NODE_H + 24)));
const minY = computed(() => Math.min(0, ...(tree.value?.nodes ?? []).map((n) => n.y)));
const shiftY = computed(() => (minY.value < 0 ? 24 - minY.value : 0));

const lines = computed(() => {
  const out: { key: string; x1: number; y1: number; x2: number; y2: number }[] = [];
  for (const node of tree.value?.nodes ?? []) {
    for (const required of node.requires) {
      const from = byId.value.get(required);
      if (from) out.push({ key: `${required}>${node.id}`, x1: from.x + NODE_W / 2, y1: from.y + NODE_H / 2 + shiftY.value, x2: node.x + NODE_W / 2, y2: node.y + NODE_H / 2 + shiftY.value });
    }
  }
  return out;
});

async function load(): Promise<void> {
  error.value = "";
  try {
    tree.value = await client.tree(props.ascended.ascended_id);
  } catch (err) {
    error.value = errorMessage(err);
  }
}
watch(() => props.ascended.ascended_id, () => { selectedId.value = null; void load(); }, { immediate: true });

const slotLabel = (slot: LoadoutSlot): string => {
  const id = tree.value?.loadout[slot];
  return id ? (byId.value.get(id)?.name ?? id) : "empty";
};
const equippedSlot = (node: TreeNodeState): LoadoutSlot | null =>
  (Object.entries(tree.value?.loadout ?? {}).find(([, id]) => id === node.id)?.[0] as LoadoutSlot | undefined) ?? null;

const costText = (node: TreeNodeState): string => (node.cost ? `${node.cost.amount} ${node.cost.tier} essence` : "free");
const detail = (node: TreeNodeState): string => {
  if (node.kind === "passive") return node.passive ? passiveText(node.passive.kind, node.passive.params) : "No passive effect.";
  const bits = [`${node.category ?? ""} ${node.percentage ?? 0}%`, `cooldown ${node.cooldown ?? 1}`];
  if (node.stat) bits.push(`+${node.stat} for ${node.duration} rounds`);
  return bits.join(", ");
};

async function learn(node: TreeNodeState): Promise<void> {
  const result = await store.learnNode(props.ascended.ascended_id, node.id);
  if (result) await load();
}

/** The replaced slot loses its node; the node leaves any other slot first. */
async function equip(node: TreeNodeState, slot: LoadoutSlot): Promise<void> {
  const next: Record<LoadoutSlot, string | null> = { ...(tree.value as TreeView).loadout };
  for (const key of Object.keys(next) as LoadoutSlot[]) if (next[key] === node.id) next[key] = null;
  next[slot] = node.id;
  await save(next);
}

async function unequip(node: TreeNodeState): Promise<void> {
  const next: Record<LoadoutSlot, string | null> = { ...(tree.value as TreeView).loadout };
  for (const key of Object.keys(next) as LoadoutSlot[]) if (next[key] === node.id) next[key] = null;
  await save(next);
}

async function save(next: Record<LoadoutSlot, string | null>): Promise<void> {
  const abilities = ABILITY_SLOTS.map((s) => next[s]).filter((id): id is string => id !== null);
  const result = await store.saveLoadout(props.ascended.ascended_id, abilities, next.p1);
  if (result) await load();
}
</script>

<template>
  <section class="tree-tab">
    <EmNotice v-if="shownError" tone="error">{{ shownError }}</EmNotice>
    <template v-if="tree">
      <div class="slots" aria-label="Equipped">
        <span v-for="slot in ABILITY_SLOTS" :key="slot" class="slot"><small>{{ slot.toUpperCase() }}</small> {{ slotLabel(slot) }}</span>
        <span class="slot"><small>PASSIVE</small> {{ slotLabel("p1") }}</span>
      </div>
      <div class="scroll">
        <div class="canvas" :style="{ width: `${width}px`, height: `${height + shiftY}px` }">
          <svg class="lines" :width="width" :height="height + shiftY" aria-hidden="true">
            <line v-for="l in lines" :key="l.key" class="tree-line" :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2" />
          </svg>
          <button
            v-for="node in tree.nodes"
            :key="node.id"
            type="button"
            class="tree-node"
            :class="{ selected: node.id === selectedId, equipped: equippedSlot(node) !== null }"
            :data-node="node.id"
            :data-state="node.state"
            :data-kind="node.kind"
            :style="{ left: `${node.x}px`, top: `${node.y + shiftY}px`, width: `${NODE_W}px`, height: `${NODE_H}px` }"
            @click="selectedId = node.id"
          >
            <strong>{{ node.name }}</strong>
            <small>{{ node.kind === "passive" ? "Passive" : titleCase(node.category ?? "") }}<template v-if="equippedSlot(node)"> · {{ equippedSlot(node)!.toUpperCase() }}</template></small>
          </button>
        </div>
      </div>
      <div v-if="selected" class="node-detail">
        <h4>{{ selected.name }}</h4>
        <p>{{ detail(selected) }}</p>
        <p class="em-num">Level {{ selected.unlock_level }} · {{ costText(selected) }}</p>
        <p v-if="selected.state === 'locked'" class="reason">{{ selected.reason }}</p>
        <EmButton v-if="selected.state === 'learnable'" class="learn" variant="primary" :disabled="store.busy" @click="learn(selected)">Learn</EmButton>
        <div v-if="selected.state === 'learned'" class="equip">
          <template v-if="selected.kind === 'ability'">
            <EmButton v-for="slot in ABILITY_SLOTS" :key="slot" :data-slot="slot" :disabled="store.busy" @click="equip(selected, slot)">Equip {{ slot.toUpperCase() }}</EmButton>
          </template>
          <EmButton v-else data-slot="p1" :disabled="store.busy" @click="equip(selected, 'p1')">Equip passive</EmButton>
          <EmButton v-if="equippedSlot(selected)" class="unequip" :disabled="store.busy" @click="unequip(selected)">Unequip</EmButton>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.slots { display: flex; flex-wrap: wrap; gap: var(--em-space-2); margin-bottom: var(--em-space-3); }
.slot { padding: 4px 10px; border: 1px solid var(--em-border); border-radius: var(--em-radius); font-size: 12px; }
.slot small { margin-right: 4px; color: var(--em-muted); font-weight: 700; }
.scroll { max-width: 100%; overflow: auto; border: 1px solid var(--em-border); border-radius: var(--em-radius); }
.canvas { position: relative; }
.lines { position: absolute; inset: 0; }
.tree-line { stroke: var(--em-border); stroke-width: 2; }
.tree-node { position: absolute; display: flex; flex-direction: column; justify-content: center; padding: 4px 8px; border: 2px solid var(--em-border); border-radius: var(--em-radius); background: var(--em-panel); color: var(--em-text); font: inherit; text-align: left; cursor: pointer; }
.tree-node strong { font-size: 13px; }
.tree-node small { color: var(--em-muted); font-size: 11px; }
.tree-node[data-state="learned"] { border-color: var(--em-accent); }
.tree-node[data-state="learnable"] { border-style: dashed; border-color: var(--em-accent); }
.tree-node[data-state="locked"] { opacity: 0.55; }
.tree-node.equipped { box-shadow: 0 0 0 2px var(--em-accent); }
.tree-node.selected { outline: 2px solid var(--em-text); }
.node-detail { display: flex; flex-direction: column; gap: 6px; margin-top: var(--em-space-3); font-size: 13px; }
.node-detail h4, .node-detail p { margin: 0; }
.reason { color: var(--em-muted); }
.equip { display: flex; flex-wrap: wrap; gap: var(--em-space-2); }
</style>
