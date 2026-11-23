<script setup lang="ts" generic="T extends string">
/** One bordered bar of filter choices, each with a status dot, a label and an optional count.
 * Copy kept in every admin app. */
export interface FilterOption<V extends string = string> {
  id: V;
  label: string;
  count?: number;
  /** Dot colour: accent (default), success, warning, danger or muted. */
  tone?: "accent" | "success" | "warning" | "danger" | "muted";
  disabled?: boolean;
}
defineProps<{ options: readonly FilterOption<T>[]; label: string }>();
const model = defineModel<T>({ required: true });
</script>

<template>
  <div class="filters" role="group" :aria-label="label">
    <button v-for="item in options" :key="item.id" type="button" :disabled="item.disabled" :aria-pressed="model === item.id" @click="model = item.id">
      <i class="dot" :class="item.tone ?? 'accent'" aria-hidden="true"></i>{{ item.label }} <strong v-if="item.count !== undefined">{{ item.count }}</strong>
    </button>
  </div>
</template>

<style scoped>
.filters { display: flex; flex-wrap: nowrap; overflow-x: auto; gap: 6px; margin-bottom: 14px; padding: 5px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); }
.filters button { display: flex; flex: 1 0 auto; white-space: nowrap; align-items: center; gap: 7px; min-height: 38px; padding: 6px 10px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--muted); font: inherit; font-size: 0.83rem; text-align: start; cursor: pointer; }
.filters button:hover:not(:disabled) { background: var(--surface); }
.filters button:disabled { opacity: 0.55; cursor: default; }
.filters button[aria-pressed="true"] { border-color: color-mix(in srgb, var(--accent) 25%, var(--border)); color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--bg)); }
.filters button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.filters strong { margin-inline-start: auto; font: 650 0.92rem/1 var(--mono); }
.dot { flex: none; width: 7px; height: 7px; border-radius: var(--radius-full); background: var(--muted); }
.dot.accent { background: var(--accent); }
.dot.success { background: var(--success); }
.dot.warning { background: var(--warning); }
.dot.danger { background: var(--danger); }
@media (max-width: 767px) { .filters button { min-height: 44px; } }
</style>
