<script setup lang="ts">
/** A selectable row for a list pane (notes, memories, tickets, documents). A
 * button: put the row content in the slot and pass `disabled`, `aria-*` and
 * `@click` as usual. `active` marks the open item. The base styles have no
 * specificity, so a page restyles the layout with its own class. */
defineProps<{ active?: boolean }>();
</script>

<template>
  <button type="button" class="list-row" :class="{ active }" :aria-current="active ? 'true' : undefined"><slot /></button>
</template>

<style scoped>
:where(.list-row) { display: flex; flex-direction: column; gap: 7px; width: 100%; padding: 14px 12px; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--text); background: transparent; font: inherit; font-size: .9em; text-align: left; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
:where(.list-row:hover:not(:disabled)) { background: var(--surface); }
:where(.list-row.active) { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
</style>
