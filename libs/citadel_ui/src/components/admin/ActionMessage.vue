<script setup lang="ts">
import { computed } from "vue";

/** The answer to an action, as coloured text with an icon and no outline: green with a check when it worked,
 * orange with a warning sign when it worked with a warning, red with the error code when it failed.
 * A failed call's text may carry its status as "[403]"; it is lifted out and shown as the code.
 * Extra content (a Retry button) goes in the default slot. Copy kept in every admin app. */
const props = defineProps<{ kind: "ok" | "warning" | "error"; text: string; code?: string }>();

const parts = computed(() => {
  const found = props.text.match(/\[(\d{3})\]\s*/);
  return { code: props.code ?? found?.[1] ?? "", text: found ? props.text.replace(found[0], "") : props.text };
});
const legacy = { ok: "notice", warning: "warning", error: "error" } as const;
</script>

<template>
  <p :class="['action-message', kind, legacy[kind]]" :role="kind === 'error' ? 'alert' : 'status'">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <template v-if="kind === 'ok'"><circle cx="12" cy="12" r="9" /><path d="m8.5 12.5 2.5 2.5 4.5-5" /></template>
      <template v-else-if="kind === 'warning'"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></template>
      <template v-else><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6M15 9l-6 6" /></template>
    </svg>
    <code v-if="parts.code" class="code">{{ parts.code }}</code>
    <span class="text">{{ parts.text }}</span>
    <slot />
  </p>
</template>

<style scoped>
.action-message { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin: 0; font-size: 0.9em; overflow-wrap: anywhere; }
.action-message svg { width: 18px; height: 18px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.action-message.ok { color: var(--success); }
.action-message.warning { color: var(--warning); }
.action-message.error { color: var(--danger); }
.code { font: 0.85em var(--mono); font-weight: 600; }
.text { min-width: 0; }
</style>
