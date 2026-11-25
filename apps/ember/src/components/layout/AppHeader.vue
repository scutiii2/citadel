<script setup lang="ts">
// The compact full-width header of the wide layout, as in the admin apps: the sidebar
// toggle, the Ember mark, the current page's name, and the account menu on the right.
// Narrow screens use the bottom bar instead, so this is hidden there.
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { useHeaderHelp } from "@citadel/ui";
import AccountMenu from "./AccountMenu.vue";
import EmberLogo from "./EmberLogo.vue";
import { useSidebar } from "../../composables/useSidebar";
import { useLogout } from "../../composables/useLogout";
import { NAV_PAGES, visiblePages } from "../../router/pages";
import { usePageVisibilityStore } from "../../stores/navigation/pageVisibility";
import { useAuthStore } from "../../stores/auth";
import { ADMIN_ACCESS_PERMISSIONS, emberAdminUrl } from "../../utils/navigation/adminLink";

const auth = useAuthStore();
const route = useRoute();
const pageVisibility = usePageVisibilityStore();
const logout = useLogout();
const { expanded, toggle } = useSidebar();

// The header is on screen from 768px up (CSS hides it below); pages hand their help to its Help button then.
const help = useHeaderHelp();
const wide = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 768px)") : null;
const syncWide = (): void => { help.ready.value = wide?.matches ?? false; };
onMounted(() => { syncWide(); wide?.addEventListener("change", syncWide); });
onBeforeUnmount(() => {
  wide?.removeEventListener("change", syncWide);
  help.ready.value = false;
  help.open.value = false;
});
watch(() => route.fullPath, () => { help.open.value = false; });

const adminUrl = emberAdminUrl();
const canAdmin = computed(() => ADMIN_ACCESS_PERMISSIONS.some(auth.hasPermission));
// The pages the account menu lists (the rest of the pages are in the sidebar).
const MENU_GROUPS = [["/capabilities", "/agents"], ["/usage", "/settings"]];
const menuGroups = computed(() => {
  const open = pageVisibility.ready ? visiblePages((p) => auth.hasPermission(p), pageVisibility.hidden) : [];
  return MENU_GROUPS.map((group) => group.flatMap((to) => open.filter((p) => p.to === to))).filter((g) => g.length > 0);
});

const EXTRA_TITLES: Record<string, string> = { "/overview": "Overview", "/account": "Account" };
/** The page's name: the nav entry with the longest matching path, else a fixed name. */
const title = computed(() => {
  const path = route.path;
  const extra = EXTRA_TITLES[path];
  if (extra) return extra;
  const match = NAV_PAGES.filter((p) => p.to === path || (p.to !== "/" && path.startsWith(`${p.to}/`))).sort((a, b) => b.to.length - a.to.length)[0];
  return match?.label ?? (path === "/" || path.startsWith("/chat") ? "Chat" : "");
});
</script>

<template>
  <header class="app-header">
    <button
      type="button"
      class="header-icon"
      aria-controls="app-sidebar"
      :aria-expanded="expanded"
      :title="expanded ? 'Collapse sidebar' : 'Expand sidebar'"
      aria-label="Sidebar"
      @click="toggle"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M9 5v14" /></svg>
    </button>
    <span class="brand"><EmberLogo class="mark" aria-hidden="true" />Ember</span>
    <p v-if="title" class="page-name">{{ title }}</p>
    <div v-if="auth.account" class="header-controls">
      <button
        v-if="help.count.value > 0"
        :ref="(el) => { help.trigger.value = el as HTMLElement | null; }"
        type="button"
        class="header-icon help"
        title="Help"
        aria-label="Help"
        aria-haspopup="true"
        :aria-expanded="help.open.value"
        @click="help.open.value = !help.open.value"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9.5 9.2a2.6 2.6 0 1 1 3.7 2.4c-.8.4-1.2 1-1.2 1.9M12 17h.01" /></svg>
      </button>
      <AccountMenu
        placement="below"
        :username="auth.account.username"
        :email="auth.account.email"
        :groups="menuGroups"
        :admin-url="canAdmin ? adminUrl : null"
        @logout="logout"
      />
    </div>
  </header>
</template>

<style scoped>
.app-header { position: relative; z-index: 31; display: flex; align-items: center; gap: 10px; flex-shrink: 0; min-height: 46px; padding: 4px 10px; border-bottom: 1px solid var(--border); background: var(--bg); }
.header-icon { display: grid; place-items: center; width: 36px; height: 36px; padding: 0; border: none; border-radius: var(--radius-md); background: var(--surface); color: var(--muted); cursor: pointer; }
.header-icon:hover { color: var(--text); }
.header-icon.help { background: transparent; }
.header-icon svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.brand { display: flex; align-items: center; gap: 8px; flex: none; color: var(--accent); font-weight: 700; font-size: 0.88rem; }
.mark { width: 22px; height: 22px; }
.page-name { min-width: 0; margin: 0; padding-inline-start: 10px; border-inline-start: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.88rem; font-weight: 600; color: var(--text); }
.header-controls { display: flex; gap: 4px; margin-inline-start: auto; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 767px) { .app-header { display: none; } }
</style>
