<script setup lang="ts">
import PanelHelp from "./PanelHelp.vue";

/** A setting's name with its own helper popover beside it: what the setting is for and the values it takes.
 * Put the help text in the default slot. Pass `for` to label a field; leave it out beside a switch. */
defineProps<{ title: string; for?: string; bare?: boolean }>();
</script>

<template>
  <span class="field-label">
    <label v-if="for" :for="for">{{ title }}</label>
    <span v-else-if="!bare" class="name">{{ title }}</span>
    <PanelHelp :title="title"><slot /></PanelHelp>
  </span>
</template>

<style scoped>
.field-label { display: inline-flex; align-items: center; gap: 2px; min-width: 0; }
label, .name { font-size: 0.9em; font-weight: 600; }
.field-label :deep(.admin-icon) { width: 28px; height: 28px; }
.field-label :deep(.admin-icon svg) { width: 15px; height: 15px; }
@media (max-width: 767px) { .field-label :deep(.admin-icon) { width: 36px; height: 36px; } }
</style>
