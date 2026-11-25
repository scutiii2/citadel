<script setup lang="ts">
import { PanelHelp } from "@citadel/ui";

/** A form label with a help icon beside it; the popover shows the paragraphs in `help`. */
defineProps<{ for: string; title: string; help?: string[] }>();
</script>

<template>
  <div class="label-row">
    <label :for="$props.for"><slot /></label>
    <PanelHelp v-if="help?.length" :title="title"><p v-for="line in help" :key="line">{{ line }}</p></PanelHelp>
  </div>
</template>

<style scoped>
.label-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 28px; }
.label-row :deep(.admin-icon) { min-width: 28px; min-height: 28px; width: 28px; height: 28px; }
</style>
