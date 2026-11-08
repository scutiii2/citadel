<script setup lang="ts">
import { computed } from "vue";
import type { CapabilityInfo } from "../../api/CommandsClient";

/** Picks the built-in capabilities an agent may call. It edits the same comma-separated
 * `tools.allow` text the form keeps: ticking a capability adds its exact tool names,
 * unticking removes them. Globs typed by hand stay as they are. */
const props = defineProps<{ modelValue: string; capabilities: CapabilityInfo[] }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const globs = computed(() => props.modelValue.split(",").map((g) => g.trim()).filter(Boolean));

function matches(glob: string, name: string): boolean {
  const source = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${source}$`).test(name);
}
function allows(name: string): boolean {
  return globs.value.length === 0 || globs.value.some((glob) => matches(glob, name));
}

const unrestricted = computed(() => globs.value.length === 0);
const rows = computed(() =>
  props.capabilities
    .filter((c) => c.tools.length > 0)
    .map((c) => ({ ...c, on: c.tools.every(allows), count: c.tools.length })),
);
// Tool schemas are sent with every model call, so this is the cost the picker is for.
const inPrompt = computed(() => props.capabilities.reduce((n, c) => n + c.tools.filter(allows).length, 0));

function toggle(capability: CapabilityInfo, on: boolean): void {
  // From "all tools" the first tick starts an explicit list instead of narrowing nothing.
  const kept = unrestricted.value ? [] : globs.value.filter((g) => !capability.tools.includes(g));
  emit("update:modelValue", (on ? [...kept, ...capability.tools] : kept).join(", "));
}
</script>

<template>
  <div class="tool-picker" data-test="tool-picker">
    <p class="hint" data-test="tool-count">
      <template v-if="unrestricted">No limit set: this agent is sent every tool ({{ inPrompt }}). Tick capabilities to limit it.</template>
      <template v-else>{{ inPrompt }} tool{{ inPrompt === 1 ? "" : "s" }} sent with every model call.</template>
    </p>
    <ul v-if="rows.length" class="list">
      <li v-for="c in rows" :key="c.name">
        <label>
          <input type="checkbox" :checked="!unrestricted && c.on" :data-test="`cap-${c.name}`" @change="toggle(c, ($event.target as HTMLInputElement).checked)" />
          <span class="name">{{ c.label || c.name }}</span>
          <span class="count">{{ c.count }} tool{{ c.count === 1 ? "" : "s" }}</span>
        </label>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tool-picker { display: grid; gap: 6px; }
.hint { margin: 0; color: var(--muted); font-size: 0.8em; }
.list { display: grid; gap: 2px; max-height: 220px; margin: 0; padding: 0; overflow: auto; list-style: none; }
label { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: var(--radius-md); cursor: pointer; font-size: 0.9em; }
label:hover { background: var(--surface); }
.name { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; }
.count { color: var(--muted); font-size: 0.85em; }
:is(input):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
