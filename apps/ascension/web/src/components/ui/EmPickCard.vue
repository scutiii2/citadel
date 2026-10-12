<script setup lang="ts">
const props = withDefaults(defineProps<{ selected: boolean; disabled?: boolean }>(), { disabled: false });
const emit = defineEmits<{ select: [] }>();
function select(): void {
  if (!props.disabled) emit("select");
}
</script>

<template>
  <div
    class="choice em-lift"
    :class="{ selected, 'em-glow': selected, 'is-off': disabled }"
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
.choice {
  --tier: var(--em-tier-common);
  box-sizing: border-box;
  width: var(--card-width);
  padding: 10px;
  border-radius: var(--em-radius);
  cursor: pointer;
}
.choice:focus-visible,
.choice.selected {
  outline: 2px solid var(--em-accent);
  outline-offset: 3px;
}
.choice.selected {
  animation: breathe 1.8s ease-in-out infinite;
}
.choice.is-off {
  opacity: 0.5;
  cursor: default;
}
@keyframes breathe {
  0%, 100% {
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--em-accent) 8%, transparent),
      0 0 8px 0 color-mix(in srgb, var(--em-accent) 20%, transparent);
  }
  50% {
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--em-accent) 20%, transparent),
      0 0 26px 6px color-mix(in srgb, var(--em-accent) 50%, transparent);
  }
}
@media (prefers-reduced-motion: reduce) {
  .choice.selected {
    animation-duration: 3.2s;
  }
}
</style>
