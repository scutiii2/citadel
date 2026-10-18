<script lang="ts">
export interface GatewayRow {
  key: number;
  gateway: string;
  model: string;
}
</script>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import type { GatewayInfo } from "../../api/AgentsAdminClient";
import { liftDragImage } from "../../utils/dragImage";

/** A draft list: moving a row carries its model, and only the parent saves it. */
const props = defineProps<{
  modelValue: GatewayRow[];
  gateways: GatewayInfo[];
  defaultGateway: string;
  busy: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [rows: GatewayRow[]] }>();
const root = ref<HTMLElement | null>(null);
const dragging = ref<number | null>(null);
const over = ref<number | null>(null);
const announcement = ref("");
const effective = (row: GatewayRow) => row.gateway || props.defaultGateway;
const available = computed(() => props.gateways.filter((gateway) =>
  !props.modelValue.some((row) => effective(row) === gateway.id)));

function usedElsewhere(id: string, key: number): boolean {
  return props.modelValue.some((row) => row.key !== key && effective(row) === id);
}

function update(key: number, field: "gateway" | "model", event: Event): void {
  if (props.busy) return;
  const value = (event.target as HTMLInputElement).value;
  emit("update:modelValue", props.modelValue.map((row) => row.key === key ? { ...row, [field]: value } : row));
}

function add(): void {
  const gateway = available.value[0];
  if (props.busy || !gateway) return;
  const key = Math.max(-1, ...props.modelValue.map((row) => row.key)) + 1;
  emit("update:modelValue", [...props.modelValue, { key, gateway: gateway.id, model: "" }]);
}

function remove(key: number): void {
  if (props.busy || props.modelValue.length <= 1) return;
  emit("update:modelValue", props.modelValue.filter((row) => row.key !== key));
}

function move(from: number, to: number, focus = false): void {
  if (props.busy || from === to || from < 0 || to < 0 || to >= props.modelValue.length) return;
  const rows = [...props.modelValue];
  const row = rows.splice(from, 1)[0];
  if (!row) return;
  rows.splice(to, 0, row);
  emit("update:modelValue", rows);
  announcement.value = `${effective(row)} moved to position ${to + 1}${to === 0 ? ", primary" : ""}.`;
  if (focus) void nextTick(() => root.value?.querySelector<HTMLButtonElement>(
    `[data-row-key="${row.key}"] [data-test="drag-handle"]`)?.focus());
}

function startDrag(event: DragEvent, row: GatewayRow): void {
  if (props.busy) { event.preventDefault(); return; }
  dragging.value = row.key;
  event.dataTransfer?.setData("text/plain", String(row.key));
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  const element = (event.currentTarget as HTMLElement).closest("li");
  if (element) liftDragImage(event, element);
}

function endDrag(): void {
  dragging.value = null;
  over.value = null;
}

function drop(key: number): void {
  const from = props.modelValue.findIndex((row) => row.key === dragging.value);
  const to = props.modelValue.findIndex((row) => row.key === key);
  endDrag();
  move(from, to);
}
</script>

<template>
  <div ref="root" class="gateway-editor">
    <div class="heading">Gateways</div>
    <p class="hint">Tried in order. The first gateway is primary.</p>
    <ol class="gateway-list" aria-label="Gateway priority">
      <li
        v-for="(row, index) in modelValue" :key="row.key" :data-row-key="row.key"
        :class="['gateway-row', { 'is-primary': index === 0, dragging: dragging === row.key, over: over === row.key && dragging !== null }]"
        data-test="gateway-row"
        @dragover.prevent="over = row.key" @drop.prevent="drop(row.key)" @dragend="endDrag"
      >
        <div class="row-head">
          <button type="button" class="grip" data-test="drag-handle" data-label="Drag to reorder" :draggable="!busy" :disabled="busy"
            :aria-label="`Reorder ${effective(row)}; use the move buttons for keyboard controls`"
            @dragstart.stop="startDrag($event, row)" @dragend="endDrag">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01" /></svg>
          </button>
          <span class="position">{{ index + 1 }}</span>
          <span :class="['role', { first: index === 0 }]">{{ index === 0 ? 'Primary' : 'Backup' }}</span>
          <label class="gateway-field">
            <span class="sr-only">{{ index === 0 ? 'Primary gateway' : `Backup gateway ${index}` }}</span>
            <select :value="row.gateway" :data-test="index === 0 ? 'gateway' : 'backup-gateway'" :disabled="busy" @change="update(row.key, 'gateway', $event)">
              <option value="" :disabled="usedElsewhere(defaultGateway, row.key)">Provider default ({{ defaultGateway }})</option>
              <option v-if="row.gateway && !gateways.some((g) => g.id === row.gateway)" :value="row.gateway">{{ row.gateway }} (unavailable)</option>
              <option v-for="gateway in gateways" :key="gateway.id" :value="gateway.id" :disabled="usedElsewhere(gateway.id, row.key)">{{ gateway.label }}</option>
            </select>
          </label>
          <button type="button" class="icon-button" data-test="move-up" :data-label="`Move ${effective(row)} up`" :aria-label="`Move ${effective(row)} up`" :disabled="busy || index === 0" @click="move(index, index - 1, true)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
          </button>
          <button type="button" class="icon-button" data-test="move-down" :data-label="`Move ${effective(row)} down`" :aria-label="`Move ${effective(row)} down`" :disabled="busy || index === modelValue.length - 1" @click="move(index, index + 1, true)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
          </button>
        </div>
        <div class="row-model">
          <label class="model-field"><span>Model override <span class="optional">(optional)</span></span>
            <input :value="row.model" :data-test="index === 0 ? 'model' : 'backup-model'" type="text" placeholder="Automatic" :disabled="busy" autocomplete="off" @input="update(row.key, 'model', $event)" />
          </label>
          <button type="button" class="remove-gateway" data-test="remove-gateway" :disabled="busy || modelValue.length === 1" :aria-label="`Remove ${effective(row)} from this agent`" @click="remove(row.key)">Remove</button>
        </div>
      </li>
    </ol>
    <div class="list-footer">
      <button type="button" class="add-gateway" data-test="add-gateway" :disabled="busy || !available.length" @click="add">＋ Add gateway</button>
      <p class="hint">Drag or use arrows to reorder. Changes apply when you save.</p>
    </div>
    <p class="sr-only" role="status" aria-live="polite">{{ announcement }}</p>
  </div>
</template>

<style scoped>
.gateway-editor { display: grid; gap: 6px; min-width: 0; }
.heading { font-size: 0.9em; font-weight: 600; }
.hint { margin: 0; font-size: 0.8em; color: var(--muted); }
.gateway-list { display: grid; gap: 8px; margin: 2px 0; padding: 0; list-style: none; }
.gateway-row { display: grid; gap: 8px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
.gateway-row.is-primary { border-color: color-mix(in srgb, var(--accent) 55%, var(--border)); }
.gateway-row.over { outline: 2px solid var(--accent); outline-offset: 1px; }
.gateway-row.dragging { opacity: 0.55; }
.row-head { display: flex; align-items: center; gap: 6px; min-width: 0; }
.position { font-size: 0.85em; }
.role { font-size: 0.75em; padding: 1px 6px; border-radius: var(--radius-sm); color: var(--muted); background: var(--code-bg); }
.role.first { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--surface)); }
.gateway-field { flex: 1; min-width: 0; }
.row-model { display: flex; align-items: flex-end; gap: 8px; padding-left: 24px; }
.model-field { display: grid; flex: 1; min-width: 0; gap: 3px; font-size: 0.85em; color: var(--muted); }
.optional { font-size: 0.9em; }
input, select { width: 100%; min-width: 0; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
button { color: var(--text); font: inherit; cursor: pointer; }
button:disabled, input:disabled, select:disabled { opacity: 0.5; cursor: default; }
.grip { display: grid; place-items: center; flex-shrink: 0; padding: 0; border: none; background: transparent; color: var(--muted); cursor: grab; }
.grip svg { width: 16px; stroke-width: 3; }
.icon-button { display: grid; place-items: center; flex-shrink: 0; padding: 4px; border: 1px solid var(--border); border-radius: var(--radius-md); background: transparent; }
svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
button.remove-gateway, button.add-gateway { padding: 4px 12px; border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; font-size: 0.85em; white-space: nowrap; }
button.remove-gateway { color: var(--danger); border-color: var(--danger); }
.list-footer { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
:is(button, input, select):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
[data-label] { position: relative; }
[data-label]:hover::after, [data-label]:focus-visible::after {
  content: attr(data-label); position: absolute; right: 0; bottom: calc(100% + 6px); z-index: 1;
  padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface); color: var(--text); font-size: 0.8rem; white-space: nowrap; pointer-events: none;
}
.grip[data-label]::after { left: 0; right: auto; }
@media (max-width: 420px) {
  .role { padding-inline: 4px; }
  .row-head { gap: 4px; }
  .row-model { padding-left: 0; }
  .optional { display: none; }
}
</style>
