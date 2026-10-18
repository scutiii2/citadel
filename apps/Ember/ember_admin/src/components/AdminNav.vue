<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AccountMenu from "./AccountMenu.vue";
import EmberLogo from "./EmberLogo.vue";
import { useTheme } from "../composables/useTheme";
import { useAuthStore } from "../stores/auth";
import { ADMIN_NAV_PAGES, ADMIN_PERMISSIONS } from "../router/pages";
import { useNavPrefsStore } from "../stores/navPrefs";
import { railPages } from "../utils/navArrangement";

const auth = useAuthStore();
const route = useRoute();
const navigation = ref<HTMLElement | null>(null);
const { theme, next, cycle } = useTheme();
const THEME_LABELS = { system: "System", light: "Light", dark: "Dark" } as const;
const navPrefs = useNavPrefsStore();
const canOpenOverview = computed(() => ADMIN_PERMISSIONS.some(auth.hasPermission));
const pages = computed(() => {
  const available = ADMIN_NAV_PAGES.filter((p) =>
  p.to !== "/overview" && (Array.isArray(p.permission) ? p.permission.some(auth.hasPermission) : auth.hasPermission(p.permission)),
  );
  const groups = railPages(available, navPrefs.prefs);
  return [...groups.pinned, ...groups.rest];
});
watch([() => route.path, pages], async () => {
  await nextTick();
  navigation.value?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
}, { immediate: true });
</script>

<template>
  <aside class="rail" aria-label="Ember Admin">
    <RouterLink v-if="canOpenOverview" to="/overview" class="wordmark" data-label="Overview" aria-label="Overview" :aria-current="route.path === '/overview' ? 'page' : undefined"><EmberLogo /></RouterLink>
    <span v-else class="wordmark" role="img" aria-label="Ember Admin"><EmberLogo /></span>
    <nav v-if="pages.length" ref="navigation" class="pages" aria-label="Admin sections">
      <RouterLink v-for="page in pages" :key="page.to" :to="page.to" :data-label="page.label" :aria-label="page.label" :aria-current="route.path === page.to ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path v-for="d in page.icon" :key="d" :d="d" /></svg>
      </RouterLink>
    </nav>
    <div class="bottom">
      <AccountMenu v-if="auth.account" :username="auth.account.username" :email="auth.account.email" @logout="auth.logout()" />
      <button v-else type="button" class="theme" :data-label="'Theme: ' + THEME_LABELS[theme] + '. Switch to ' + THEME_LABELS[next()]" :aria-label="'Theme: ' + THEME_LABELS[theme] + '. Switch to ' + THEME_LABELS[next()]" @click="cycle">
        <svg v-if="theme === 'light'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        <svg v-else-if="theme === 'dark'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></svg>
        <svg v-else viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
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
.pages, .bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.pages { margin-top: 8px; }
.bottom { margin-top: auto; }
.wordmark {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  text-decoration: none;
}
.wordmark svg { width: 100%; height: 100%; }
.pages a, .bottom a, button {
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
.pages a:hover, .bottom a:hover, button:hover { color: var(--text); background: var(--bg); }
a[aria-current="page"]:not(.wordmark) {
  color: var(--text);
  background: var(--bg);
  box-shadow: inset 2px 0 0 var(--accent);
}
svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
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
  .rail {
    flex-direction: row;
    width: 100%;
    height: var(--rail-height);
    padding: 0 4px env(safe-area-inset-bottom, 0px);
    gap: 4px;
    border-right: none;
    border-top: 1px solid var(--border);
  }
  .wordmark { width: 28px; height: 28px; flex-shrink: 0; }
  .pages { flex: 1; min-width: 0; margin: 0; flex-direction: row; justify-content: flex-start; overflow-x: auto; scrollbar-width: none; gap: 0; }
  .bottom { flex-direction: row; flex-shrink: 0; margin: 0; gap: 0; }
  .pages a, .bottom a, button { width: 44px; height: 44px; flex-shrink: 0; }
  a[aria-current="page"]:not(.wordmark) { box-shadow: inset 0 -2px 0 var(--accent); }
  [data-label]:hover::after, [data-label]:focus-visible::after {
    left: 50%; top: auto; bottom: calc(100% + 8px); transform: translateX(-50%);
  }
  .wordmark[data-label]::after { left: 0; transform: none; }
  .bottom [data-label]::after { left: auto; right: 0; transform: none; }
  .pages [data-label]::after { display: none; }
}
</style>
