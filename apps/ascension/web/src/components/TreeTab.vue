<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useAscensionClient, type LoadoutSlot, type OwnedAscended, type TreeNodeState, type TreeView } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { effectText, passiveText, titleCase } from "../utils/ascension";
import { layoutTree } from "../utils/treeLayout";
import { spriteFor, spriteFocus } from "../utils/sprites";
import EmButton from "./ui/EmButton.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmIcon from "./ui/EmIcon.vue";
import type { IconName } from "./ui/icons";

/** One Ascended's ability tree: nodes at their own places, learn a node, equip it in a slot. */
const props = defineProps<{ ascended: OwnedAscended }>();
const store = useAscensionStore();
const client = useAscensionClient();

const NODE_W = 156;
const NODE_H = 116;
const ICON_RADIUS = 30;
const showNames = ref(true);

const tree = ref<TreeView | null>(null);
const selectedId = ref<string | null>(null);
const error = ref("");
const loading = ref(false);
const scroll = ref<HTMLElement | null>(null);
const zoom = ref(1);
let request = 0;
let viewportInitialized = false;
let drag: { x: number; y: number; left: number; top: number } | null = null;
/** A failed load, else the failure of the last learn or equip (the store keeps it). */
const shownError = computed(() => error.value || store.error);

const slotList = computed(() => tree.value?.slots ?? []);
const equipSlots = computed(() => slotList.value.filter((slot) => slot.kind === selected.value?.kind
  && (slot.branches === null || (selected.value?.branch != null && slot.branches.includes(selected.value.branch)))));

const selected = computed(() => tree.value?.nodes.find((n) => n.id === selectedId.value) ?? null);
const byId = computed(() => new Map((tree.value?.nodes ?? []).map((n) => [n.id, n])));
const layout = computed(() => layoutTree(tree.value?.nodes ?? []));
const point = (id: string) => layout.value.positions.get(id) ?? layout.value.center;
const width = computed(() => layout.value.width);
const height = computed(() => layout.value.height);
const info = computed(() => store.catalog?.ascendeds.find(n => n.id === props.ascended.ascended_id));
const portrait = computed(() => spriteFor(info.value?.art, "main_card"));
const highlighted = computed(() => {
  const ids = new Set<string>();
  function visit(id: string): void {
    if (ids.has(id)) return;
    ids.add(id);
    for (const required of byId.value.get(id)?.requires ?? []) visit(required);
  }
  if (selectedId.value) visit(selectedId.value);
  return ids;
});
const rootNodes = computed(() => tree.value?.nodes.filter(n => n.root || n.requires.length === 0) ?? []);
const nodeIcon = (node: TreeNodeState): IconName => node.kind === "passive" ? "flame" : node.category === "DEFENSE" ? "shield" : node.category === "SUPPORT" ? "arrow" : node.category === "FLEE" ? "feather" : node.category === "INTERCEPT" ? "ascended" : "sword";
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
  zoom.value = Math.max(0.3, Math.min(1, scroll.value.clientWidth / width.value, 700 / height.value));
  scroll.value.scrollTo?.({ left: 0, top: 0 });
}
function changeZoom(delta: number): void { zoom.value = Math.max(0.3, Math.min(1.5, zoom.value + delta)); }
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
  const out: { key: string; path: string; highlighted: boolean; shared: boolean; learned: boolean }[] = [];
  for (const node of tree.value?.nodes ?? []) {
    for (const required of node.requires) {
      const from = byId.value.get(required);
      if (from) {
        const a = point(from.id), b = point(node.id);
        const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
        const cut = ICON_RADIUS + 4;
        out.push({ key: `${required}>${node.id}`, path: `M ${a.x + dx / length * cut} ${a.y + dy / length * cut} L ${b.x - dx / length * cut} ${b.y - dy / length * cut}`, highlighted: highlighted.value.has(node.id) && highlighted.value.has(required), shared: layout.value.sharedIds.has(node.id), learned: from.state === 'learned' && node.state === 'learned' });
      }
    }
  }
  return out;
});
const rootLines = computed(() => rootNodes.value.map(node => {
  const a = layout.value.center, b = point(node.id);
  const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
  return { id: node.id, highlighted: highlighted.value.has(node.id), path: `M ${a.x + dx / length * 70} ${a.y + dy / length * 70} L ${b.x - dx / length * 34} ${b.y - dy / length * 34}` };
}));

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
    if (token !== request) return;
    if (!viewportInitialized && scroll.value) {
      zoom.value = (scroll.value?.clientWidth ?? 0) >= 600 && result.nodes.length <= 20 ? Math.max(0.8, Math.min(1, (scroll.value?.clientWidth ?? 0) / width.value)) : 1;
      await nextTick();
      if (token !== request) return;
      scroll.value?.scrollTo?.({ left: Math.max(0, layout.value.center.x * zoom.value - (scroll.value?.clientWidth ?? 0) / 2), top: Math.max(0, layout.value.center.y * zoom.value - 340) });
      viewportInitialized = true;
    }
  } catch (err) {
    if (token === request) error.value = errorMessage(err);
  } finally {
    if (token === request) loading.value = false;
  }
}
watch(() => [props.ascended.ascended_id, props.ascended.level, props.ascended.tier_id, props.ascended.stars, props.ascended.copies], (current, previous) => {
  if (current[0] !== previous?.[0]) { tree.value = null; selectedId.value = null; viewportInitialized = false; }
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
  const next: Partial<Record<LoadoutSlot, string | null>> = { ...(tree.value as TreeView).loadout };
  for (const key of Object.keys(next) as LoadoutSlot[]) if (next[key] === node.id) next[key] = null;
  next[slot] = node.id;
  await save(next);
}

async function unequip(node: TreeNodeState): Promise<void> {
  const next: Partial<Record<LoadoutSlot, string | null>> = { ...(tree.value as TreeView).loadout };
  for (const key of Object.keys(next) as LoadoutSlot[]) if (next[key] === node.id) next[key] = null;
  await save(next);
}

async function save(next: Partial<Record<LoadoutSlot, string | null>>): Promise<void> {
  const result = await store.saveLoadout(props.ascended.ascended_id, next);
  if (result) await load();
}
</script>

<template>
  <section class="tree-tab">
    <EmNotice v-if="shownError" tone="error">{{ shownError }}</EmNotice>
    <p v-if="loading" class="muted" role="status">Loading ability tree…</p>
    <EmButton v-if="error" @click="load">Retry</EmButton>
    <template v-if="tree">
      <div class="tree-heading"><div><h3>Ability tree</h3><p class="muted em-num">{{ learned }} / {{ tree.nodes.length }} learned · {{ layout.branches.length }} paths from the Ascended</p></div><div class="tree-controls"><EmButton :aria-pressed="showNames" @click="showNames = !showNames">{{ showNames ? 'Hide names' : 'Show names' }}</EmButton><EmButton aria-label="Zoom out" @click="changeZoom(-0.1)">−</EmButton><span class="em-num">{{ Math.round(zoom * 100) }}%</span><EmButton aria-label="Zoom in" @click="changeZoom(0.1)">+</EmButton><EmButton @click="fit">Fit tree</EmButton></div></div>
      <p class="path-labels muted">Paths: {{ layout.branches.map(b => b.label).join(' · ') }}</p>
      <div class="slots" aria-label="Equipped">
        <button v-for="slot in slotList" :key="slot.id" type="button" class="slot" :disabled="!tree.loadout[slot.id]" @click="selectedId = tree.loadout[slot.id] ?? null"><small>{{ slot.id.toUpperCase() }}</small> {{ slotLabel(slot.id) }}<small v-if="slot.branches" class="branch-hint">{{ slot.branches.join(" / ") }}</small></button>
      </div>
      <div class="tree-layout">
      <div class="graph-area">
      <div ref="scroll" class="scroll" tabindex="0" aria-label="Ability tree graph. Use the zoom controls or scroll to explore." @pointerdown="startPan" @pointermove="pan" @pointerup="drag = null" @pointercancel="drag = null" @lostpointercapture="drag = null" @wheel.ctrl.prevent="changeZoom($event.deltaY < 0 ? 0.1 : -0.1)">
        <div class="canvas-wrap" :style="{ width: `${width * zoom}px`, height: `${height * zoom}px` }">
        <div class="canvas" :style="{ width: `${width}px`, height: `${height}px`, transform: `scale(${zoom})` }">
          <svg class="lines" :width="width" :height="height" aria-hidden="true">
            <circle class="orbit" :cx="layout.center.x" :cy="layout.center.y" r="210" />
            <circle class="orbit" :cx="layout.center.x" :cy="layout.center.y" r="360" />
            <path v-for="l in rootLines" :key="l.id" class="origin-line" :class="{ highlighted: l.highlighted }" :d="l.path" />
            <path v-for="l in lines" :key="l.key" class="tree-line" :class="{ learned: l.learned, highlighted: l.highlighted, 'shared-link': l.shared, concealed: l.shared && !l.highlighted }" :d="l.path" />
          </svg>
          <div class="origin-hub" :style="{ left: `${layout.center.x}px`, top: `${layout.center.y}px` }">
            <div class="hub-portrait"><img v-if="portrait" :src="portrait" :alt="ascended.name" :style="{ objectPosition: `50% ${spriteFocus(info?.art, 'main_card')}%` }" /><EmIcon v-else name="ascended" :size="44" /></div>
            <strong>{{ ascended.name }}</strong><small class="em-num">Level {{ ascended.level }} · Origin</small>
          </div>
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
            :aria-label="`${node.name}, ${node.kind === 'passive' ? 'passive' : 'active ability'}, ${stateLabel(node)}`"
            :title="`${node.name} · ${node.kind === 'passive' ? 'Passive' : titleCase(node.category ?? '')} · ${stateLabel(node)}`"
            :style="{ left: `${point(node.id).x - NODE_W / 2}px`, top: `${point(node.id).y - 32}px`, width: `${NODE_W}px`, height: `${NODE_H}px` }"
            @click="selectedId = node.id"
          >
            <span class="node-symbol" aria-hidden="true"><svg class="node-shape" viewBox="0 0 70 70"><circle v-if="node.kind === 'passive'" class="node-outline" cx="35" cy="35" r="30" /><polygon v-else class="node-outline" points="20,4 50,4 66,20 66,50 50,66 20,66 4,50 4,20" /></svg><EmIcon :name="nodeIcon(node)" :size="26" /><span v-if="equippedSlot(node)" class="equipped-mark"><EmIcon name="check" :size="11" /></span></span>
            <strong v-show="showNames" class="node-name">{{ node.name }}</strong>
            <small v-show="showNames" class="node-state">{{ stateLabel(node) }}</small>
            <small v-if="layout.sharedIds.has(node.id) && showNames" class="shared-label">Shared · {{ node.requires.length }} prerequisites</small>
          </button>
        </div>
        </div>
      </div>
      <div class="legend"><span><svg viewBox="0 0 20 20"><polygon points="6,1 14,1 19,6 19,14 14,19 6,19 1,14 1,6"/></svg>Active ability</span><span><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="9"/></svg>Passive</span><span>✓ Learned / equipped</span><span>◇ Available</span><span>Locked · level required</span></div>
      <p class="graph-help muted">Drag the background to pan · Ctrl + scroll to zoom · Tab to select nodes</p>
      <p v-if="layout.sharedIds.size" class="graph-help muted">Select a shared ability to reveal its connections across paths.</p>
      </div>
      <aside v-if="selected" class="node-detail" aria-label="Selected ability" aria-live="polite">
        <small class="em-eyebrow">Selected {{ selected.kind === 'ability' ? 'active ability' : 'passive' }}<template v-if="selected.branch"> · {{ titleCase(selected.branch) }}</template></small>
        <h4>{{ selected.name }}</h4>
        <span class="selected-state">{{ stateLabel(selected) }}</span>
        <p>{{ detail(selected) }}</p>
        <dl v-if="selected.kind === 'ability'" class="ability-facts"><div><dt>Power</dt><dd class="em-num">{{ selected.percentage }}%</dd></div><div><dt>Cooldown</dt><dd class="em-num">{{ selected.cooldown }} rounds</dd></div></dl>
        <h5>{{ selected.state === 'learned' ? 'Unlock requirements (already learned)' : 'Requirements' }}</h5>
        <ul class="requirements"><li v-for="item in requirements" :key="item.label" :class="{ met: item.met }"><span>{{ item.met ? '✓' : '○' }} {{ item.label }}</span><small v-if="item.hint">{{ item.hint }}</small></li></ul>
        <p v-if="selected.state === 'locked'" class="reason">{{ selected.reason }}</p>
        <EmButton v-if="selected.state === 'learnable'" class="learn" variant="primary" :disabled="store.busy || loading" @click="learn(selected)">Learn · {{ costText(selected) }}</EmButton>
        <div v-if="selected.state === 'learned'" class="equip">
          <EmButton v-for="slot in equipSlots" :key="slot.id" :data-slot="slot.id" :disabled="store.busy || loading" @click="equip(selected, slot.id)">Equip {{ slot.id.toUpperCase() }}<small>{{ slotLabel(slot.id) }}</small></EmButton>
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
.path-labels { font-size: 12px; margin-bottom: var(--em-space-3); }
.slots { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: var(--em-space-2); margin-bottom: var(--em-space-4); }
button.slot { padding: 10px 12px; min-height: var(--em-target); border: 1px solid var(--em-divider); border-radius: var(--em-radius); font: inherit; font-size: 12px; color: var(--em-text); background: var(--em-bg); text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.slot:disabled { cursor: default; color: var(--em-muted); }
.slot small { display: block; color: var(--em-muted); font-weight: 700; }
.tree-layout { display: grid; grid-template-columns: minmax(0, 1fr) 264px; gap: var(--em-space-4); align-items: start; }
.graph-area { min-width: 0; }
.scroll { max-width: 100%; max-height: 700px; min-height: 340px; overflow: auto; border: 1px solid var(--em-divider); border-radius: var(--em-radius); background: var(--em-bg); cursor: grab; }
.canvas { position: relative; transform-origin: top left; }
.canvas-wrap { margin-inline: auto; }
.branch-hint { margin-top: 2px; font-weight: 400; }
.lines { position: absolute; inset: 0; }
.tree-line, .origin-line { stroke: var(--em-divider); stroke-width: 2; fill: none; }
.origin-line { stroke: var(--em-success); }
.tree-line.learned { stroke: var(--em-success); }
.tree-line.highlighted, .origin-line.highlighted { stroke: var(--em-accent); stroke-width: 3; }
.tree-line.shared-link { stroke-dasharray: 5 6; }
.tree-line.concealed { visibility: hidden; }
.orbit { stroke: var(--em-divider); stroke-width: 1; stroke-dasharray: 2 10; fill: none; opacity: 0.35; }
button.tree-node { position: absolute; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 2px; padding: 0; border: 0; border-radius: var(--em-radius); background: transparent; color: var(--em-text); font: inherit; text-align: center; cursor: pointer; }
.tree-node strong { font-size: 12px; line-height: 1.25; }
.tree-node small { color: var(--em-muted); font-size: 10px; line-height: 1.2; }
.node-symbol { position: relative; display: flex; align-items: center; justify-content: center; width: 64px; height: 64px; flex: none; color: var(--em-muted); }
.node-shape { position: absolute; inset: 0; width: 100%; height: 100%; }
.node-outline { stroke: var(--em-border); stroke-width: 1.8; fill: var(--em-panel); }
.node-symbol > .em-icon { position: relative; }
.tree-node[data-state="learned"] .node-outline { stroke: var(--em-success); fill: var(--em-success-surface); }
.tree-node[data-state="learned"] .node-symbol { color: var(--em-success); }
.tree-node[data-state="learned"] .node-state { color: var(--em-success); }
.tree-node[data-state="learnable"] .node-outline { stroke: var(--em-accent); fill: var(--em-warning-surface); stroke-dasharray: 3 3; }
.tree-node[data-state="learnable"] .node-symbol { color: var(--em-accent); }
.tree-node[data-state="learnable"] .node-state { color: var(--em-accent); }
.tree-node.selected .node-outline { stroke: var(--em-accent); stroke-width: 3; stroke-dasharray: none; }
.tree-node.selected .node-symbol { color: var(--em-accent); filter: drop-shadow(0 0 5px color-mix(in srgb, var(--em-accent) 35%, transparent)); }
.equipped-mark { position: absolute; right: 0; top: 0; width: 16px; height: 16px; border-radius: var(--radius-full); background: var(--em-success); color: var(--em-bg); display: flex; align-items: center; justify-content: center; }
.origin-hub { position: absolute; width: 148px; transform: translate(-50%, -66px); display: flex; flex-direction: column; align-items: center; gap: 6px; pointer-events: none; text-align: center; }
.hub-portrait { display: flex; align-items: center; justify-content: center; width: 132px; height: 132px; border: 2px solid var(--em-accent); padding: 6px; border-radius: var(--radius-full); color: var(--em-accent); background: var(--em-bg); }
.hub-portrait img { width: 100%; height: 100%; object-fit: cover; border-radius: var(--radius-full); }
.origin-hub strong { font-size: 14px; }
.origin-hub small { color: var(--em-accent); font-size: 11px; }
.legend { display: flex; flex-wrap: wrap; gap: var(--em-space-3); color: var(--em-muted); font-size: 11px; margin-top: var(--em-space-2); }
.legend span { display: flex; align-items: center; gap: 5px; }
.legend svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.5; }
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
