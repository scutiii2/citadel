<script setup lang="ts">
import { computed } from "vue";
import type { LoadoutSlot, TreeView } from "../api/AscensionClient";
import EmIcon from "./ui/EmIcon.vue";
import placeholder from "../assets/abilities/ability_placeholder.webp";

const props = defineProps<{ tree: TreeView | null; ascendedId: string }>();
const emit = defineEmits<{ select: [id: string | null] }>();
const slots: LoadoutSlot[] = ["p1", "p2", "a1", "a2", "a3", "a4"];
const nodes = computed(() => new Map(props.tree?.nodes.map(node => [node.id, node]) ?? []));
const art = import.meta.glob<string>("../../../ascended/*/icon_*.webp", { eager: true, import: "default" });
const node = (slot: LoadoutSlot) => nodes.value.get(props.tree?.loadout[slot] ?? "");
const slotLabel = (slot: LoadoutSlot) => node(slot)?.name ?? (props.tree && !props.tree.slots.some(s => s.id === slot) ? "Not available on this Ascended" : "Empty slot");
</script>

<template>
  <div class="ability-slots" aria-label="Equipped abilities">
    <button v-for="slot in slots" :key="slot" class="ability-slot" type="button" :data-kind="slot.startsWith('p') ? 'passive' : 'ability'" :aria-label="`${slot.toUpperCase()}: ${slotLabel(slot)}`" :title="slotLabel(slot)" :disabled="!!tree && !tree.slots.some(s => s.id === slot)" @click="emit('select', tree?.loadout[slot] ?? null)">
      <span class="slot-art">
        <svg class="slot-outline" viewBox="0 0 100 100" aria-hidden="true"><circle v-if="slot.startsWith('p')" cx="50" cy="50" r="46" /><polygon v-else points="30,4 70,4 96,30 96,70 70,96 30,96 4,70 4,30" /></svg>
        <img v-if="node(slot)" :src="art[`../../../ascended/${ascendedId}/icon_${node(slot)!.id}.webp`] ?? placeholder" alt="" />
        <EmIcon v-else :name="slot.startsWith('p') ? 'flame' : 'sword'" :size="26" />
      </span><small>{{ slot.toUpperCase() }}</small>
    </button>
  </div>
</template>

<style scoped>
.ability-slots{display:grid;grid-template-columns:repeat(6,minmax(0,64px));gap:10px}.ability-slot{display:flex;flex-direction:column;align-items:center;gap:5px;min-width:0;padding:0;border:0;background:none;color:#c8e8f4;font:inherit;cursor:pointer}.slot-art{position:relative;display:grid;place-items:center;width:100%;aspect-ratio:1;color:#69d8f6}.slot-art>.slot-outline{position:absolute;inset:0;width:100%;height:100%;fill:#071d2ddd;stroke:#e9ba82;stroke-width:2}.slot-art :deep(.em-icon){position:relative}.slot-art img{position:relative;width:60%;height:60%;object-fit:contain;image-rendering:pixelated}.ability-slot small{font-size:11px}.ability-slot:hover .slot-art>.slot-outline{stroke:#83e9ff;fill:#12374c}.ability-slot:focus-visible{outline:2px solid var(--em-accent);outline-offset:4px}
.ability-slot:disabled{opacity:.35;cursor:default}
</style>
