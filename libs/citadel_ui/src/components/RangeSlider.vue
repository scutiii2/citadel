<script setup lang="ts">
import { computed, useAttrs } from "vue";

/** A split-track range slider: a thick active track, a slim vertical handle and a gap around it.
 * A native `<input type="range">` sits invisibly on top and stays the source of truth, so the
 * keyboard, touch and screen readers work as usual. Give it a name (`aria-label` or a `<label for>`).
 * Extra attributes (`id`, `step`, `disabled`, `aria-*`, `@input`) go to the input; `class` and `style` to the wrapper. */
defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{ modelValue: number | string; min?: number | string; max?: number | string }>(), { min: 0, max: 100 });
const emit = defineEmits<{ "update:modelValue": [value: number | string] }>();
const attrs = useAttrs();

const inputAttrs = computed(() => {
  const { class: _class, style: _style, ...rest } = attrs;
  return rest;
});
/** 0 to 1: where the handle sits. Clamped, so a value outside the range cannot push a track past the control. */
const fraction = computed(() => {
  const min = Number(props.min), span = Number(props.max) - min;
  return span > 0 ? Math.min(1, Math.max(0, (Number(props.modelValue) - min) / span)) : 0;
});
// The stop dot ends the remaining track; with less than 8% left there is no room for it.
const showStop = computed(() => fraction.value < 0.92);

function onInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  emit("update:modelValue", typeof props.modelValue === "number" ? Number(value) : value);
}
</script>

<template>
  <div class="split-slider" :class="attrs.class" :style="[{ '--v': fraction }, attrs.style as never]">
    <span class="track active" aria-hidden="true" />
    <span class="track rest" aria-hidden="true"><i v-if="showStop" class="stop" /></span>
    <span class="handle" aria-hidden="true" />
    <input v-bind="inputAttrs" type="range" :min="min" :max="max" :value="modelValue" @input="onInput" />
  </div>
</template>

<style scoped>
.split-slider {
  --thumb: 16px; /* the input's real thumb: the handle's hit area, fixed while the visible handle narrows */
  --gap: 6px;
  --track: 16px;
  --x: calc(var(--thumb) / 2 + (100% - var(--thumb)) * var(--v));
  position: relative;
  display: block;
  min-width: 0;
  height: 28px;
  border-radius: var(--radius-md);
}
.track {
  position: absolute;
  top: 50%;
  height: var(--track);
  translate: 0 -50%;
  background: var(--accent);
}
.active {
  left: 0;
  width: max(0px, calc(var(--x) - var(--gap)));
  border-radius: var(--radius-full) var(--radius-sm) var(--radius-sm) var(--radius-full);
}
.rest {
  right: 0;
  width: max(0px, calc(100% - var(--x) - var(--gap)));
  border-radius: var(--radius-sm) var(--radius-full) var(--radius-full) var(--radius-sm);
  background: var(--border);
}
.stop {
  position: absolute;
  top: 50%;
  right: 6px;
  width: 4px;
  height: 4px;
  translate: 0 -50%;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.handle {
  position: absolute;
  top: 50%;
  left: var(--x);
  width: 4px;
  height: 26px;
  translate: -50% -50%;
  border-radius: var(--radius-full);
  background: var(--accent);
  transition: width 0.15s ease;
}
.split-slider:has(input:active) .handle { width: 2px; }
input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}
input::-webkit-slider-thumb { width: var(--thumb); height: 28px; }
input::-moz-range-thumb { width: var(--thumb); height: 28px; }
.split-slider:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.split-slider:has(input:disabled) { opacity: 0.55; }
.split-slider:has(input:disabled) input { cursor: default; }
@media (pointer: coarse) { .split-slider { height: 44px; } }
</style>
