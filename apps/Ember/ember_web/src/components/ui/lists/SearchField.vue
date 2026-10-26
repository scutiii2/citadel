<script setup lang="ts">
/** A search box: magnifier, a search input and an optional trailing slot (a
 * submit button, a sort menu). `v-model` is the text; `label` is the accessible
 * name. Other attributes (`placeholder`, `maxlength`, `disabled`) go to the
 * input. Spacing around the box is the page's, set with its own class. */
defineOptions({ inheritAttrs: false });
defineProps<{ label: string }>();
const model = defineModel<string>({ required: true });
</script>

<template>
  <label class="search-field" :class="$attrs.class">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
    <input v-model="model" type="search" :aria-label="label" v-bind="{ ...$attrs, class: undefined }" />
    <slot />
  </label>
</template>

<style scoped>
.search-field { display: flex; align-items: center; gap: 8px; min-width: 0; padding: 9px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); }
.search-field:focus-within { border-color: var(--accent); }
.search-field svg { flex-shrink: 0; width: 16px; height: 16px; fill: none; stroke: var(--muted); stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.search-field input { flex: 1; min-width: 0; width: 100%; padding: 0; border: 0; border-radius: 0; background: transparent; color: var(--text); font: inherit; font-size: .9em; }
.search-field > :slotted(button) { flex-shrink: 0; }
@media (max-width: 767px) {
  .search-field { min-height: 44px; }
  .search-field input { font-size: max(1em, 16px); }
  .search-field > :slotted(button) { min-height: 44px; }
}
</style>
