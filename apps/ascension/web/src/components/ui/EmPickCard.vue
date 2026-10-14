<script setup lang="ts">
const props = withDefaults(defineProps<{ selected: boolean; disabled?: boolean }>(), { disabled: false });
const emit = defineEmits<{ select: [] }>();
function select(): void {
  if (!props.disabled) emit("select");
}
</script>

<template>
  <div
    class="choice"
    :class="{ selected, 'is-off': disabled }"
    role="radio"
    :tabindex="disabled ? -1 : 0"
    :aria-checked="selected"
    :aria-disabled="disabled"
    @click="select"
    @keydown.enter.prevent="select"
    @keydown.space.prevent="select"
  ><slot /></div>
</template>

<style scoped>
/* The slotted card is the whole picture: no padding or ring around it. A picked card glows and
 * drifts up and down; a hovered one rises, grows a little and blooms in its own tier colour. */
.choice {
  --tier: var(--em-tier-common);
  box-sizing: border-box;
  width: var(--card-width);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: transform 180ms ease-out;
}
.choice :deep(.card) { transition: filter 180ms ease-out; }
.choice:not(.is-off):hover { transform: translateY(-4px) scale(1.03); }
.choice:not(.is-off):hover :deep(.card) {
  filter: drop-shadow(0 0 10px color-mix(in srgb, var(--tier) 55%, transparent));
}
.choice:focus-visible {
  outline: 2px solid var(--em-accent);
  outline-offset: 3px;
}
.choice.selected {
  animation: breathe 1.8s ease-in-out infinite;
}
.choice.selected:not(.is-off) :deep(.card) {
  animation: card-glow 1.8s ease-in-out infinite;
}
.choice.is-off {
  opacity: 0.5;
  cursor: default;
}
@keyframes breathe {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}
@keyframes card-glow {
  0%, 100% { filter: drop-shadow(0 0 5px color-mix(in srgb, var(--tier) 35%, transparent)); }
  50% { filter: drop-shadow(0 0 12px color-mix(in srgb, var(--tier) 60%, transparent)); }
}
</style>
