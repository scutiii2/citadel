<script setup lang="ts">
import { ref } from "vue";
import { pointBelow, type MenuPoint } from "../../../components/ui/menus/menuPoint";

// The "..." button that opens a row's or folder's menu just under itself.
// pointerdown.stop: an open menu closes on any press outside it, so a press on
// this button must not reach it; the sidebar toggles instead.
defineProps<{ label: string; expanded: boolean }>();
const emit = defineEmits<{ open: [point: MenuPoint] }>();

const button = ref<HTMLButtonElement | null>(null);
defineExpose({ button });
</script>

<template>
  <button
    ref="button"
    type="button"
    :class="['more', { expanded }]"
    :title="label"
    :aria-label="label"
    aria-haspopup="menu"
    :aria-expanded="expanded"
    @pointerdown.stop
    @click.stop="emit('open', pointBelow(button))"
  >
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
      <circle cx="5" cy="12" r="1.8" fill="currentColor" />
      <circle cx="12" cy="12" r="1.8" fill="currentColor" />
      <circle cx="19" cy="12" r="1.8" fill="currentColor" />
    </svg>
  </button>
</template>
