<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { ADMIN_NAV_PAGES, ADMIN_PERMISSIONS, CONFIG_ISSUES_ICON } from "../router/pages";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import { useNavPrefsStore } from "../stores/navPrefs";
import { railPages } from "../utils/navArrangement";
import { ADMIN_APPS, adminAppUrl } from "@citadel/ui";

/** The sidebar: Overview, the permitted pages in the saved arrangement, Config issues while there are
 * any, and shortcuts to the other admin apps. Collapsed it shows named icons. */
defineProps<{ expanded: boolean }>();
const auth = useAuthStore();
const route = useRoute();
const navigation = ref<HTMLElement | null>(null);
const navPrefs = useNavPrefsStore();
const configIssues = useConfigIssuesStore();
const shortcuts = ADMIN_APPS.filter((app) => app.port !== 26501);
const allowed = (permission: string | string[]) => (Array.isArray(permission) ? permission.some(auth.hasPermission) : auth.hasPermission(permission));
const overview = computed(() => (ADMIN_PERMISSIONS.some(auth.hasPermission) ? ADMIN_NAV_PAGES.find((page) => page.to === "/overview") : undefined));
const pages = computed(() => {
  const groups = railPages(ADMIN_NAV_PAGES.filter((page) => page.to !== "/overview" && allowed(page.permission)), navPrefs.prefs);
  return [...(overview.value ? [overview.value] : []), ...groups.pinned, ...groups.rest];
});
const showConfigAlert = computed(() => configIssues.active.length > 0);
const alertLabel = computed(() => {
  const parts = ([[configIssues.errorCount, "error"], [configIssues.warningCount, "warning"]] as const)
    .filter(([n]) => n)
    .map(([n, word]) => `${n} ${word}${n === 1 ? "" : "s"}`);
  return `Config issues: ${parts.join(", ")}`;
});
watch([() => route.path, pages], async () => {
  await nextTick();
  navigation.value?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
}, { immediate: true });
</script>

<template>
  <aside id="portcullis-sidebar" class="sidebar" :class="{ expanded }" aria-label="Portcullis Admin">
    <nav ref="navigation" aria-label="Admin sections">
      <RouterLink v-for="page in pages" :key="page.to" :to="page.to" :title="page.label" :aria-label="page.label"
        :aria-current="route.path === page.to ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path v-for="d in page.icon" :key="d" :d="d" /></svg>
        <span v-if="expanded">{{ page.label }}</span>
      </RouterLink>
      <RouterLink v-if="showConfigAlert" to="/config-issues" class="alert" :class="configIssues.errorCount > 0 ? 'has-errors' : 'has-warnings'"
        :title="alertLabel" :aria-label="alertLabel" :aria-current="route.path === '/config-issues' ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path v-for="d in CONFIG_ISSUES_ICON" :key="d" :d="d" /></svg>
        <span v-if="expanded">Config issues</span>
        <span class="count">{{ configIssues.active.length }}</span>
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
/* Config issues: red while any error exists, amber when only warnings. */
.alert { --tone: var(--warning); color: var(--tone); }
.alert.has-errors { --tone: var(--status-failed); }
.alert .count { min-width: 16px; height: 16px; padding: 0 4px; border-radius: var(--radius-full); font-size: 0.7rem; line-height: 16px; text-align: center; color: var(--bg); background: var(--tone); }
.sidebar:not(.expanded) .alert .count { position: absolute; inset: 0 0 auto auto; }
.expanded .alert .count { margin-inline-start: auto; }
@media (max-width: 767px) {
  .sidebar.expanded { width: 100%; max-height: 45dvh; border-inline-end: 0; border-bottom: 1px solid var(--border); }
  .sidebar a { min-height: 44px; }
}
</style>
