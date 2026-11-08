<script setup lang="ts">
/** A selectable row for a list pane (notes, memories, tickets, documents). A
 * button: put the row content in the slot and pass `disabled`, `aria-*` and
 * `@click` as usual. `active` marks the open item. The base styles have no
 * specificity, so a page restyles the layout with its own class. An optional
 * actions slot shares the selected frame while keeping controls outside the
 * selection button. Existing rows without actions keep their button root. */

defineOptions({ inheritAttrs: false });
defineProps<{ active?: boolean }>();
</script>

<template>
  <div v-if="$slots.actions" class="list-row-frame" :class="{ active }">
    <button type="button" class="list-row" :aria-current="active ? 'true' : undefined" v-bind="$attrs"><slot /></button>
    <div class="list-row-actions"><slot name="actions" /></div>
  </div>
  <button v-else type="button" class="list-row" :class="{ active }" :aria-current="active ? 'true' : undefined" v-bind="$attrs"><slot /></button>
</template>

<style scoped>
:where(.list-row) { display: flex; flex-direction: column; gap: 7px; width: 100%; padding: 14px 12px; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--text); background: transparent; font: inherit; font-size: .9em; text-align: left; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
:where(.list-row:hover:not(:disabled)) { background: var(--surface); }
:where(.list-row.active) { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
:where(.list-row-frame) { border: 1px solid transparent; border-radius: var(--radius-md); }
:where(.list-row-frame.active) { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
.list-row-frame > .list-row { border: 0; }
.list-row-frame.active > .list-row { background: transparent; }
.list-row-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 0 12px 12px; }
</style>
