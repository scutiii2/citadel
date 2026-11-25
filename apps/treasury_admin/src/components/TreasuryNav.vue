<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { TREASURY_PAGES } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { ADMIN_APPS, adminAppUrl } from "@citadel/ui";

/** The sidebar: the permitted pages, then shortcuts to the other admin apps. Collapsed it shows named icons. */
defineProps<{ expanded: boolean }>();
const auth = useAuthStore();
const route = useRoute();
const pages = computed(() => TREASURY_PAGES.filter((p) => [p.permission].flat().some((name) => auth.hasPermission(name))));
const shortcuts = ADMIN_APPS.filter((app) => app.port !== 26505);
</script>

<template>
  <aside id="treasury-sidebar" class="sidebar" :class="{ expanded }" aria-label="Treasury Admin">
    <nav v-if="pages.length" aria-label="Treasury sections">
      <RouterLink v-for="page in pages" :key="page.to" :to="page.to" :title="page.label" :aria-label="page.label"
        :aria-current="route.path === page.to ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path v-for="d in page.icon" :key="d" :d="d" /></svg>
        <span v-if="expanded">{{ page.label }}</span>
      </RouterLink>
    </nav>
    <nav v-if="shortcuts.length" class="shortcuts" aria-label="Other admin apps">
      <a v-for="app in shortcuts" :key="app.port" :href="adminAppUrl(app.port)" :title="app.name" :aria-label="app.name">
        <span class="initial" aria-hidden="true">{{ app.letter }}</span><span v-if="expanded">{{ app.name }}</span>
      </a>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar { display: flex; flex-direction: column; flex: none; width: 52px; padding: 8px; gap: 12px; border-inline-end: 1px solid var(--border); background: var(--bg); overflow-y: auto; scrollbar-gutter: stable; }
.sidebar.expanded { width: 210px; }
nav { display: grid; gap: 4px; }
.shortcuts { margin-top: auto; padding-top: 8px; border-top: 1px solid var(--border); }
a { position: relative; display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 36px; border-radius: var(--radius-md); color: var(--muted); text-decoration: none; font-size: 0.84rem; }
.expanded a { justify-content: flex-start; padding-inline: 8px; }
a:hover, a[aria-current="page"] { background: var(--surface); color: var(--text); }
a[aria-current="page"] { box-shadow: inset 2px 0 var(--accent); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
svg { flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.initial { width: 18px; text-align: center; font-weight: 600; }
@media (max-width: 767px) {
  .sidebar.expanded { width: 100%; max-height: 45dvh; border-inline-end: 0; border-bottom: 1px solid var(--border); }
  .sidebar a { min-height: 44px; }
}
</style>
