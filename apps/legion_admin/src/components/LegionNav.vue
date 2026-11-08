<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useTheme } from "../composables/useTheme";
import { LEGION_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const { theme, next, cycle } = useTheme();
const LABELS = { system: "System", light: "Light", dark: "Dark" } as const;
const pages = computed(() => LEGION_PAGES.filter((p) => auth.hasPermission(p.permission)));
const themeLabel = computed(() => `Theme: ${LABELS[theme.value]}. Switch to ${LABELS[next()]}`);
</script>

<template>
  <aside class="rail" aria-label="Legion Admin">
    <span class="wordmark" role="img" aria-label="Legion Admin">L</span>
    <nav v-if="pages.length" class="pages" aria-label="Legion sections">
      <RouterLink v-for="page in pages" :key="page.to" :to="page.to" :data-label="page.label" :aria-label="page.label" :aria-current="route.path === page.to ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path v-for="d in page.icon" :key="d" :d="d" /></svg>
      </RouterLink>
    </nav>
    <div class="bottom">
      <button type="button" :data-label="themeLabel" :aria-label="themeLabel" @click="cycle">
        <svg v-if="theme === 'light'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        <svg v-else-if="theme === 'dark'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>
        <svg v-else viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
      </button>
      <button v-if="auth.account" type="button" data-label="Log out" aria-label="Log out" @click="auth.logout()">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 52px;
  flex-shrink: 0;
  padding: 10px 0;
  border-right: 1px solid var(--border);
  background: var(--surface);
  position: relative;
  z-index: 30;
}
.pages, .bottom { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.pages { margin-top: 8px; }
.bottom { margin-top: auto; }
.wordmark { display: grid; place-items: center; width: 36px; height: 36px; font-weight: 700; color: var(--accent); }
.pages a, button {
  position: relative;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--muted);
  background: transparent;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
}
.pages a:hover, button:hover { color: var(--text); background: var(--bg); }
a[aria-current="page"] { color: var(--text); background: var(--bg); box-shadow: inset 2px 0 0 var(--accent); }
svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
[data-label]:hover::after, [data-label]:focus-visible::after {
  content: attr(data-label);
  position: absolute;
  left: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  white-space: nowrap;
  font-size: 0.85rem;
  color: var(--text);
  background: var(--surface);
  pointer-events: none;
}
@media (max-width: 767px) {
  .rail { flex-direction: row; width: 100%; height: var(--rail-height); padding: 0 4px env(safe-area-inset-bottom, 0px); gap: 4px; border-right: none; border-top: 1px solid var(--border); }
  .wordmark { width: 28px; height: 28px; flex-shrink: 0; }
  .pages { flex: 1; min-width: 0; margin: 0; flex-direction: row; justify-content: flex-start; overflow-x: auto; scrollbar-width: none; gap: 0; }
  .bottom { flex-direction: row; flex-shrink: 0; margin: 0; gap: 0; }
  .pages a, button { width: 44px; height: 44px; flex-shrink: 0; }
  a[aria-current="page"] { box-shadow: inset 0 -2px 0 var(--accent); }
  [data-label]::after { display: none; }
}
</style>
