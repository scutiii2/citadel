<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed, ref, watch, onMounted, onUnmounted } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import DraftActions from "../components/admin/DraftActions.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import "../components/admin/admin.css";
import SettingRow from "../components/SettingRow.vue";
import SidebarEditor from "../components/SidebarEditor.vue";
import SegmentedControl from "../components/SegmentedControl.vue";
import { DEFAULT_THEME, useTheme, type Theme } from "../composables/useTheme";
import { useNavPrefsStore } from "../stores/navPrefs";
import { useAuthStore } from "../stores/auth";
import { isDefault } from "../utils/navArrangement";

const { theme, setTheme } = useTheme();
const navPrefs = useNavPrefsStore();
const auth = useAuthStore();
const saved = computed(() => ({
  sidebar: { order: [...navPrefs.prefs.order], pinned: [...navPrefs.prefs.pinned], hidden: [...navPrefs.prefs.hidden] },
}));
const draft = ref(structuredClone(saved.value));
const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(saved.value));
watch(saved, (next, previous) => {
  if (JSON.stringify(draft.value.sidebar) === JSON.stringify(previous.sidebar)) {
    draft.value.sidebar = structuredClone(next.sidebar);
  }
});
function revert(): void { draft.value = structuredClone(saved.value); }
function save(): void {
  if (!dirty.value) return;
  if (JSON.stringify(draft.value.sidebar) !== JSON.stringify(saved.value.sidebar)) navPrefs.update(draft.value.sidebar);
  revert();
}
watch(() => auth.account?.id, revert);
const discardOpen = ref(false);
let discardAnswer: ((discard: boolean) => void) | null = null;
function answerDiscard(discard: boolean): void {
  if (discard) revert();
  discardOpen.value = false;
  discardAnswer?.(discard);
  discardAnswer = null;
}
onBeforeRouteLeave(() => {
  if (!dirty.value) return true;
  discardOpen.value = true;
  return new Promise<boolean>(resolve => { discardAnswer = resolve; });
});
function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value) { event.preventDefault(); event.returnValue = ""; }
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onUnmounted(() => { window.removeEventListener("beforeunload", beforeUnload); answerDiscard(false); });
const query = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const onlyModified = ref(false);
const options: { value: Theme; label: string }[] = [
  { value: "system", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" },
];
const themeModified = computed(() => theme.value !== DEFAULT_THEME);
const sidebarModified = computed(() => !isDefault(draft.value.sidebar));
const count = computed(() => Number(themeModified.value) + Number(sidebarModified.value));
function matches(words: string): boolean {
  return query.value.toLowerCase().trim().split(/\s+/).every(word => words.includes(word));
}
const showTheme = computed(() => matches("appearance theme light dark system color") && (!onlyModified.value || themeModified.value));
const showSidebar = computed(() => matches("sidebar pages order pin hide navigation rearrange drag") && (!onlyModified.value || sidebarModified.value));
</script>

<template>
  <PageLayout class="settings-view admin-panel" title="Settings" wide>
    <section class="admin-panel-card" aria-labelledby="settings-title">
      <header class="admin-panel-head">
        <h2 id="settings-title">Preferences</h2>
        <div class="admin-panel-tools tools">
          <PanelHelp title="Preferences"><p>Your own appearance and navigation settings for Portcullis Admin.</p><p>Theme applies instantly and is saved on this device. Sidebar preferences apply when you save. They are separate for each account.</p></PanelHelp>
          <button v-if="count || onlyModified" type="button" class="chip" :aria-pressed="onlyModified" @click="onlyModified = !onlyModified">{{ count }} modified</button>
          <DraftActions :dirty="dirty" :saving="false" label="settings changes" @cancel="discardOpen = true" @save="save" />
          <AdminSearch ref="searchField" v-model="query" label="Search settings" />
        </div>
      </header>
      <div class="settings-body">
        <p v-if="navPrefs.error" class="error" role="alert">{{ navPrefs.error }}</p>
        <section v-if="showTheme" aria-label="Appearance">
          <h3>Appearance</h3>
          <p class="lede">Applies at once and is saved on this device.</p>
          <div class="card"><SettingRow setting-id="appearance-theme" label="Theme" description="Light, dark, or follow your system." :modified="themeModified" @reset="setTheme(DEFAULT_THEME)">
            <SegmentedControl :model-value="theme" @update:model-value="setTheme" :options="options" aria-label="Theme" />
          </SettingRow></div>
        </section>
        <section v-if="showSidebar" aria-label="Sidebar"><h3>Sidebar</h3><p class="lede">Applies when you save. Separate for each account.</p><div class="card"><SidebarEditor v-model="draft.sidebar" /></div></section>
        <p v-if="!showTheme && !showSidebar" class="muted">No settings match your filters. <button type="button" class="chip" @click="query = ''; onlyModified = false; searchField?.focus()">Clear filters</button></p>
      </div>
    </section>
    <ConfirmModal v-if="discardOpen" :open="discardOpen" title="Discard unsaved settings?" message="Your settings changes have not been saved." confirm-label="Discard changes" @confirm="answerDiscard(true)" @close="answerDiscard(false)" />
  </PageLayout>
</template>

<style scoped>
.settings-body { display: grid; gap: 24px; padding: 18px 16px 20px; }
.lede { margin: -4px 0 10px; font-size: 0.85em; color: var(--muted); }
.settings-body h3 { margin: 0 0 8px; font-size: 1em; }
.card { padding: 4px 16px 6px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-contrast); }
</style>
