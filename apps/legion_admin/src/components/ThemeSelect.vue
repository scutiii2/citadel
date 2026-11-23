<script setup lang="ts">
import { useTheme, type Theme } from "../composables/useTheme";

/** The labeled Dark, Light and System choice. Copy kept in every admin app. */
const { theme, setTheme } = useTheme();
</script>

<template>
  <label class="theme-field">
    <span>Theme</span>
    <span class="theme-select">
      <select :value="theme" @change="setTheme(($event.target as HTMLSelectElement).value as Theme)">
        <option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option>
      </select>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
    </span>
  </label>
</template>

<style scoped>
.theme-field { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.theme-select { position: relative; display: inline-flex; align-items: center; }
.theme-select select { appearance: none; min-width: 96px; min-height: 36px; padding: 4px 30px 4px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); color: var(--text); font: inherit; cursor: pointer; }
.theme-select select:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.theme-select svg { position: absolute; inset-inline-end: 8px; width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; pointer-events: none; }
</style>
