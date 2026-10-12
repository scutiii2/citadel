<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useAscensionClient, type LoadoutSlot, type OwnedAscended, type TreeNodeState, type TreeView } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { effectText, passiveText, titleCase } from "../utils/ascension";
import { layoutTree } from "../utils/treeLayout";
import EmButton from "./ui/EmButton.vue";
import EmNotice from "./ui/EmNotice.vue";

/** One Ascended's ability tree: nodes at their own places, learn a node, equip it in a slot. */
const props = defineProps<{ ascended: OwnedAscended }>();
const store = useAscensionStore();
const client = useAscensionClient();

const NODE_W = 156;
const NODE_H = 88;
const ABILITY_SLOTS: LoadoutSlot[] = ["a1", "a2", "a3"];

const tree = ref<TreeView | null>(null);
const selectedId = ref<string | null>(null);
const error = ref("");
const loading = ref(false);
const scroll = ref<HTMLElement | null>(null);
const zoom = ref(1);
let request = 0;
let drag: { x: number; y: number; left: number; top: number } | null = null;
/** A failed load, else the failure of the last learn or equip (the store keeps it). */
const shownError = computed(() => error.value || store.error);

const selected = computed(() => tree.value?.nodes.find((n) => n.id === selectedId.value) ?? null);
const byId = computed(() => new Map((tree.value?.nodes ?? []).map((n) => [n.id, n])));
const positions = computed(() => layoutTree(tree.value?.nodes ?? []));
const point = (id: string) => positions.value.get(id) ?? { x: 24, y: 24 };
const width = computed(() => Math.max(300, ...Array.from(positions.value.values()).map(p => p.x + NODE_W + 24)));
const height = computed(() => Math.max(200, ...Array.from(positions.value.values()).map(p => p.y + NODE_H + 24)));
const learned = computed(() => tree.value?.nodes.filter(n => n.state === 'learned').length ?? 0);
const requirements = computed(() => {
  if (!selected.value || !tree.value) return [];
  const node = selected.value;
  const items = [{ label: `Level ${node.unlock_level}`, met: tree.value.level >= node.unlock_level, hint: `You are level ${tree.value.level}` }];
  for (const id of node.requires) items.push({ label: `${byId.value.get(id)?.name ?? id} learned`, met: byId.value.get(id)?.state === 'learned', hint: '' });
  if (node.cost) items.push({ label: costText(node), met: (tree.value.essences[node.cost.tier] ?? 0) >= node.cost.amount, hint: `You have ${tree.value.essences[node.cost.tier] ?? 0}` });
  return items;
});
function fit(): void {
  if (!scroll.value?.clientWidth) return;
  zoom.value = Math.max(0.4, Math.min(1, scroll.value.clientWidth / width.value));
  scroll.value.scrollTo?.({ left: 0, top: 0 });
}
function changeZoom(delta: number): void { zoom.value = Math.max(0.4, Math.min(1.5, zoom.value + delta)); }
function startPan(event: PointerEvent): void {
  if ((event.target as HTMLElement).closest('button') || event.button !== 0 || event.pointerType === 'touch' || !scroll.value) return;
  drag = { x: event.clientX, y: event.clientY, left: scroll.value.scrollLeft, top: scroll.value.scrollTop };
  scroll.value.setPointerCapture?.(event.pointerId);
}
function pan(event: PointerEvent): void {
  if (!drag || !scroll.value) return;
  scroll.value.scrollLeft = drag.left - (event.clientX - drag.x);
  scroll.value.scrollTop = drag.top - (event.clientY - drag.y);
}

const lines = computed(() => {
  const out: { key: string; x1: number; y1: number; x2: number; y2: number }[] = [];
  for (const node of tree.value?.nodes ?? []) {
    for (const required of node.requires) {
      const from = byId.value.get(required);
      if (from) out.push({ key: `${required}>${node.id}`, x1: point(from.id).x + NODE_W, y1: point(from.id).y + NODE_H / 2, x2: point(node.id).x, y2: point(node.id).y + NODE_H / 2 });
    }
  }
  return out;
});

async function load(): Promise<void> {
  const token = ++request;
  const id = props.ascended.ascended_id;
  error.value = "";
  loading.value = true;
  try {
    const result = await client.tree(id);
    if (token !== request) return;
    tree.value = result;
    if (!selected.value) selectedId.value = result.nodes.find(n => n.state === 'learnable')?.id ?? result.nodes[0]?.id ?? null;
    await nextTick();
    if ((scroll.value?.clientWidth ?? 0) >= 600) fit();
    else zoom.value = 1;
  } catch (err) {
    if (token === request) error.value = errorMessage(err);
  } finally {
    if (token === request) loading.value = false;
  }
}
watch(() => [props.ascended.ascended_id, props.ascended.level, props.ascended.tier_id, props.ascended.stars, props.ascended.copies], (current, previous) => {
  if (current[0] !== previous?.[0]) { tree.value = null; selectedId.value = null; }
  void load();
}, { immediate: true });

const slotLabel = (slot: LoadoutSlot): string => {
  const id = tree.value?.loadout[slot];
  return id ? (byId.value.get(id)?.name ?? id) : "empty";
};
const equippedSlot = (node: TreeNodeState): LoadoutSlot | null =>
  (Object.entries(tree.value?.loadout ?? {}).find(([, id]) => id === node.id)?.[0] as LoadoutSlot | undefined) ?? null;
const stateLabel = (node: TreeNodeState): string => equippedSlot(node) ? `✓ Equipped · ${equippedSlot(node)!.toUpperCase()}` : node.state === 'learned' ? '✓ Learned' : node.state === 'learnable' ? '◇ Available' : `Locked · Lv ${node.unlock_level}`;

const costText = (node: TreeNodeState): string => (node.cost ? `${node.cost.amount} ${node.cost.tier} essence` : "free");
const detail = (node: TreeNodeState): string => {
  if (node.kind === "passive") return node.passive ? passiveText(node.passive.kind, node.passive.params) : "No passive effect.";
  const bits = [`${node.category ?? ""} ${node.percentage ?? 0}%`, `cooldown ${node.cooldown ?? 1}`];
  if (node.stat) bits.push(`+${node.stat} for ${node.duration} rounds`);
  const effect = effectText(node.effects);
  return effect ? `${bits.join(", ")}. ${effect}.` : bits.join(", ");
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
    <p v-if="loading" class="muted" role="status">Loading ability tree…</p>
    <EmButton v-if="error" @click="load">Retry</EmButton>
    <template v-if="tree">
      <div class="tree-heading"><div><h3>Ability tree</h3><p class="muted em-num">{{ learned }} / {{ tree.nodes.length }} learned · Select a node to inspect it</p></div><div class="tree-controls"><EmButton aria-label="Zoom out" @click="changeZoom(-0.1)">−</EmButton><span class="em-num">{{ Math.round(zoom * 100) }}%</span><EmButton aria-label="Zoom in" @click="changeZoom(0.1)">+</EmButton><EmButton @click="fit">Fit tree</EmButton></div></div>
      <div class="slots" aria-label="Equipped">
        <button v-for="slot in ABILITY_SLOTS" :key="slot" type="button" class="slot" :disabled="!tree.loadout[slot]" @click="selectedId = tree.loadout[slot]"><small>{{ slot.toUpperCase() }}</small> {{ slotLabel(slot) }}</button>
        <button type="button" class="slot" :disabled="!tree.loadout.p1" @click="selectedId = tree.loadout.p1"><small>PASSIVE</small> {{ slotLabel("p1") }}</button>
      </div>
      <div class="tree-layout">
      <div class="graph-area">
      <div ref="scroll" class="scroll" tabindex="0" aria-label="Ability tree graph. Use the zoom controls or scroll to explore." @pointerdown="startPan" @pointermove="pan" @pointerup="drag = null" @pointercancel="drag = null" @lostpointercapture="drag = null" @wheel.ctrl.prevent="changeZoom($event.deltaY < 0 ? 0.1 : -0.1)">
        <div :style="{ width: `${width * zoom}px`, height: `${height * zoom}px` }">
        <div class="canvas" :style="{ width: `${width}px`, height: `${height}px`, transform: `scale(${zoom})` }">
          <svg class="lines" :width="width" :height="height" aria-hidden="true">
            <path v-for="l in lines" :key="l.key" class="tree-line" :d="`M ${l.x1} ${l.y1} C ${l.x1 + 24} ${l.y1}, ${l.x2 - 24} ${l.y2}, ${l.x2} ${l.y2}`" />
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
            :aria-pressed="node.id === selectedId"
            :aria-label="`${node.name}, ${stateLabel(node)}`"
            :style="{ left: `${point(node.id).x}px`, top: `${point(node.id).y}px`, width: `${NODE_W}px`, height: `${NODE_H}px` }"
            @click="selectedId = node.id"
          >
            <strong>{{ node.name }}</strong>
            <small class="category">{{ node.kind === "passive" ? "Passive" : titleCase(node.category ?? "") }}</small>
            <small class="node-state">{{ stateLabel(node) }}</small>
          </button>
        </div>
        </div>
      </div>
      <div class="legend"><span>✓ Learned / equipped</span><span>◇ Available</span><span>Locked · level required</span></div>
      <p class="graph-help muted">Drag the background to pan · Ctrl + scroll to zoom · Tab to select nodes</p>
      </div>
      <aside v-if="selected" class="node-detail" aria-label="Selected ability" aria-live="polite">
        <small class="em-eyebrow">Selected {{ selected.kind }}</small>
        <h4>{{ selected.name }}</h4>
        <span class="selected-state">{{ stateLabel(selected) }}</span>
        <p>{{ detail(selected) }}</p>
        <dl v-if="selected.kind === 'ability'" class="ability-facts"><div><dt>Power</dt><dd class="em-num">{{ selected.percentage }}%</dd></div><div><dt>Cooldown</dt><dd class="em-num">{{ selected.cooldown }} rounds</dd></div></dl>
        <h5>{{ selected.state === 'learned' ? 'Unlock requirements (already learned)' : 'Requirements' }}</h5>
        <ul class="requirements"><li v-for="item in requirements" :key="item.label" :class="{ met: item.met }"><span>{{ item.met ? '✓' : '○' }} {{ item.label }}</span><small v-if="item.hint">{{ item.hint }}</small></li></ul>
        <p v-if="selected.state === 'locked'" class="reason">{{ selected.reason }}</p>
        <EmButton v-if="selected.state === 'learnable'" class="learn" variant="primary" :disabled="store.busy || loading" @click="learn(selected)">Learn · {{ costText(selected) }}</EmButton>
        <div v-if="selected.state === 'learned'" class="equip">
          <template v-if="selected.kind === 'ability'">
            <EmButton v-for="slot in ABILITY_SLOTS" :key="slot" :data-slot="slot" :disabled="store.busy || loading" @click="equip(selected, slot)">Equip {{ slot.toUpperCase() }}<small>{{ slotLabel(slot) }}</small></EmButton>
          </template>
          <EmButton v-else data-slot="p1" :disabled="store.busy || loading" @click="equip(selected, 'p1')">Equip passive</EmButton>
          <EmButton v-if="equippedSlot(selected)" class="unequip" :disabled="store.busy || loading" @click="unequip(selected)">Unequip</EmButton>
        </div>
        <p v-if="selected.state !== 'learned'" class="muted">Learning unlocks this {{ selected.kind }}. Equip it in a battle slot to use it.</p>
      </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.tree-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--em-space-3); margin-bottom: var(--em-space-4); }
.tree-heading h3 { margin: 0; font-size: 20px; }
.tree-heading p { margin: 4px 0 0; font-size: 12px; }
.tree-controls { display: flex; align-items: center; gap: var(--em-space-2); }
.slots { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--em-space-2); margin-bottom: var(--em-space-4); }
button.slot { padding: 10px 12px; min-height: var(--em-target); border: 1px solid var(--em-divider); border-radius: var(--em-radius); font: inherit; font-size: 12px; color: var(--em-text); background: var(--em-bg); text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.slot:disabled { cursor: default; color: var(--em-muted); }
.slot small { display: block; color: var(--em-muted); font-weight: 700; }
.tree-layout { display: grid; grid-template-columns: minmax(0, 1fr) 264px; gap: var(--em-space-4); align-items: start; }
.graph-area { min-width: 0; }
.scroll { max-width: 100%; max-height: 560px; min-height: 260px; overflow: auto; border: 1px solid var(--em-divider); border-radius: var(--em-radius); background: var(--em-bg); cursor: grab; }
.canvas { position: relative; transform-origin: top left; }
.lines { position: absolute; inset: 0; }
.tree-line { stroke: var(--em-border); stroke-width: 2; fill: none; }
.tree-node { position: absolute; display: flex; flex-direction: column; justify-content: center; gap: 4px; padding: 10px 12px; border: 1px solid var(--em-border); border-radius: var(--em-radius); background: var(--em-panel); color: var(--em-text); font: inherit; text-align: left; cursor: pointer; }
.tree-node strong { font-size: 13px; }
.tree-node small { color: var(--em-muted); font-size: 11px; }
.tree-node[data-state="learned"] { border-color: var(--em-success); }
.tree-node[data-state="learned"] .node-state { color: var(--em-success); }
.tree-node[data-state="learnable"] { border-color: var(--em-accent); }
.tree-node[data-state="learnable"] .node-state { color: var(--em-accent); }
.tree-node.selected { box-shadow: 0 0 0 3px var(--em-accent); }
.legend { display: flex; flex-wrap: wrap; gap: var(--em-space-3); color: var(--em-muted); font-size: 11px; margin-top: var(--em-space-2); }
.graph-help { font-size: 11px; margin-top: var(--em-space-2); }
.node-detail { display: flex; flex-direction: column; gap: var(--em-space-3); padding: var(--em-space-4); border: 1px solid var(--em-accent); background: var(--em-bg); border-radius: var(--em-radius); font-size: 13px; }
.node-detail h4, .node-detail p { margin: 0; }
.node-detail h4 { font-size: 20px; }
.node-detail h5 { font-size: 13px; margin: 0; }
.selected-state { color: var(--em-accent); }
.ability-facts { display: flex; gap: var(--em-space-5); margin: 0; padding: var(--em-space-3) 0; border-block: 1px solid var(--em-divider); }
.ability-facts dt { color: var(--em-muted); font-size: 11px; }
.ability-facts dd { margin: 0; font-weight: 600; }
.requirements { padding: 0; margin: 0; list-style: none; display: flex; flex-direction: column; gap: var(--em-space-2); }
.requirements li small { display: block; color: var(--em-muted); }
.requirements .met { color: var(--em-success); }
.reason { color: var(--em-muted); }
.equip { display: flex; flex-direction: column; gap: var(--em-space-2); }
.equip small { display: block; color: var(--em-muted); font-weight: 400; font-size: 11px; margin-left: var(--em-space-2); }
@media (max-width: 1100px) { .tree-layout { grid-template-columns: minmax(0, 1fr); } .slots { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
