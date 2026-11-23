<script setup lang="ts">
/** One number of the Admin overview, with a small label above it. `value` is
 * null while the count loads; `unavailable` says the server could not give it
 * (never shown as zero). `warn` colours it for counts that want attention. */
defineProps<{ label: string; value: number | null; warn?: boolean; unavailable?: boolean }>();
</script>

<template>
  <div class="tile">
    <span v-if="$slots.default" :class="['icon', { warn: warn && value }]" aria-hidden="true"><slot /></span>
    <span class="label">{{ label }}</span>
    <span v-if="unavailable" class="value unavailable">Unavailable</span>
    <span v-else :class="['value', { warn: warn && value }]">{{ value ?? "–" }}</span>
  </div>
</template>

<style scoped>
.tile {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.icon {
  position: absolute;
  right: 16px;
  top: 16px;
  display: flex;
  color: var(--muted);
}
.icon.warn {
  color: var(--warning);
}
.label {
  padding-right: 24px;
  font-size: 0.8em;
  color: var(--muted);
}
.value {
  font-size: 1.6em;
  font-weight: 600;
  line-height: 1.2;
}
.value.unavailable {
  font-size: 0.95em;
  font-weight: 500;
  color: var(--muted);
}
.value.warn {
  color: var(--warning);
}
</style>
