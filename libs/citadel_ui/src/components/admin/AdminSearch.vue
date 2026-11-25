<script setup lang="ts">
import { ref } from "vue";

defineProps<{ label: string }>();
const query = defineModel<string>({ required: true });
const field = ref<HTMLInputElement>();

defineExpose({ focus: () => field.value?.focus() });
</script>

<template>
  <label class="search">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="5.5" /><path d="m15 15 4 4" /></svg>
    <input ref="field" v-model="query" type="search" :aria-label="label" :placeholder="label" />
  </label>
</template>

<style scoped>
.search { display: flex; flex: 1; align-items: center; gap: 6px; min-width: 0; padding-inline: 9px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--muted); }
.search:focus-within { outline: 2px solid var(--accent); outline-offset: -2px; }
.search svg { width: 18px; height: 18px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; }
.search input:focus-visible { outline: none; }
.search input[type="search"] { width: 100%; min-width: 0; min-height: 34px; padding: 4px 0; border: 0; outline: none; background: transparent; color: var(--text); font-size: 0.83rem; }
.search input::placeholder { color: var(--muted); }
@media (max-width: 767px) {
  .search input { min-height: 44px; }
}
</style>
