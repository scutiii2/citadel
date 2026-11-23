<script setup lang="ts">
/** The tab strip of a drawer form. The form keeps every panel mounted (`v-show`) so a draft survives a tab change;
 * give each panel `role="tabpanel"`, `id="<prefix>-panel-<id>"` and `aria-labelledby="<prefix>-tab-<id>"`. */
const props = defineProps<{ modelValue: string; items: { id: string; label: string; disabled?: boolean; title?: string }[]; prefix: string; label: string }>();
const emit = defineEmits<{ "update:modelValue": [id: string] }>();

function move(step: number): void {
  const items = props.items.filter((item) => !item.disabled);
  const next = items[(items.findIndex((item) => item.id === props.modelValue) + step + items.length) % items.length];
  if (!next) return;
  emit("update:modelValue", next.id);
  document.getElementById(`${props.prefix}-tab-${next.id}`)?.focus();
}
</script>

<template>
  <div class="form-tabs" role="tablist" :aria-label="label">
    <button v-for="item in items" :id="`${prefix}-tab-${item.id}`" :key="item.id" type="button" role="tab"
      :aria-selected="modelValue === item.id" :aria-controls="`${prefix}-panel-${item.id}`" :tabindex="modelValue === item.id ? 0 : -1"
      :disabled="item.disabled" :title="item.title"
      :data-test="`tab-${item.id}`" @click="emit('update:modelValue', item.id)" @keydown.right.prevent="move(1)" @keydown.left.prevent="move(-1)">{{ item.label }}</button>
  </div>
</template>

<style scoped>
.form-tabs { display: flex; gap: 4px; padding: 3px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); overflow-x: auto; }
.form-tabs button { flex: 1 0 auto; min-height: 36px; padding: 0 12px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--muted); font: inherit; font-weight: 600; cursor: pointer; white-space: nowrap; }
.form-tabs button[aria-selected="true"] { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--text); }
.form-tabs button:disabled { opacity: 0.5; cursor: not-allowed; }
.form-tabs button:hover:not([aria-selected="true"]) { color: var(--text); }
.form-tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
</style>
