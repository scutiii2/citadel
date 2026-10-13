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
.choice :deep(.card) { transition: box-shadow 180ms ease-out; }
.choice:not(.is-off):hover { transform: translateY(-4px) scale(1.03); }
.choice:not(.is-off):hover :deep(.card) {
  box-shadow:
    inset 0 0 0 2px #091421,
    inset 0 0 0 3px color-mix(in srgb, var(--tier) 55%, transparent),
    0 5px 0 #040c13,
    0 0 28px 4px color-mix(in srgb, var(--tier) 40%, transparent),
    0 12px 24px #0009;
}
.choice:focus-visible {
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
    transform: translateY(0);
    box-shadow: 0 0 8px 0 color-mix(in srgb, var(--em-accent) 20%, transparent);
  }
  50% {
    transform: translateY(-3px);
    box-shadow: 0 0 26px 6px color-mix(in srgb, var(--em-accent) 50%, transparent);
  }
}
</style>
