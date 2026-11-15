<script setup lang="ts">
import { ref, useId } from "vue";

defineOptions({ inheritAttrs: false });
defineProps<{ label: string; id?: string; disabled?: boolean }>();
const model = defineModel<string>({ default: "" });
const inputId = useId();
const visible = ref(false);
</script>

<template>
  <div class="password-field">
    <label :for="id ?? inputId">{{ label }}</label>
    <div class="password-control">
      <input v-bind="$attrs" :id="id ?? inputId" v-model="model" :type="visible ? 'text' : 'password'" :disabled="disabled" />
      <button
        type="button"
        :aria-label="visible ? 'Hide password' : 'Show password'"
        :aria-pressed="visible"
        :aria-controls="id ?? inputId"
        :disabled="disabled"
        @mousedown.prevent
        @click="visible = !visible"
      >{{ visible ? 'Hide' : 'Show' }}</button>
    </div>
  </div>
</template>

<style scoped>
.password-field { display: grid; gap: 4px; min-width: 0; }
.password-field label { font-size: 0.9em; font-weight: 600; }
.password-control { position: relative; min-width: 0; }
.password-field .password-control input {
  width: 100%;
  min-width: 0;
  min-height: 44px;
  padding: 8px 68px 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-weight: normal;
  color: var(--text);
  background: var(--bg);
}
.password-field .password-control input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.password-control button {
  position: absolute;
  top: 0;
  right: 4px;
  bottom: 0;
  min-width: 56px;
  padding: 0 8px;
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.85em;
  font-weight: 600;
  color: var(--accent);
  background: transparent;
  cursor: pointer;
}
.password-control button:hover { background: color-mix(in srgb, var(--accent) 10%, var(--bg)); }
.password-control button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.password-control button:disabled { opacity: 0.5; cursor: default; }
</style>
