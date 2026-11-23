<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import { useTheme } from "../composables/useTheme";
import { useAuthStore } from "../stores/auth";

defineProps<{ title: string; expanded: boolean }>();
defineEmits<{ toggle: [] }>();
const auth = useAuthStore();
const route = useRoute();
const { theme, setTheme } = useTheme();
const panel = ref<"notifications" | "help" | "profile">();
const trigger = ref<HTMLElement>();
const header = ref<HTMLElement>();
const offline = ref<string[]>();
const loading = ref(false);
const canReadStatus = computed(() => auth.hasPermission("agents.manage") && auth.hasPermission("chat.use"));
const initials = computed(() => auth.account?.username.slice(0, 2).toUpperCase() ?? "");
let request = 0;

async function refresh() {
  const generation = ++request;
  offline.value = undefined;
  loading.value = canReadStatus.value;
  if (!canReadStatus.value) return;
  try {
    const status = await agentsAdminClient.live();
    if (generation === request) offline.value = Object.entries(status).filter(([, item]) => item.status === "offline").map(([id]) => id);
  } catch {
    // Without live data the header cannot infer which agents are offline.
  } finally {
    if (generation === request) loading.value = false;
  }
}

function toggle(next: typeof panel.value, event: MouseEvent) {
  panel.value = panel.value === next ? undefined : next;
  if (panel.value) trigger.value = event.currentTarget as HTMLElement;
  if (panel.value === "notifications") void refresh();
}

function dismiss() {
  if (!panel.value) return;
  panel.value = undefined;
  trigger.value?.focus();
}

function closeOutside(event: PointerEvent) {
  if (event.target instanceof Node && !header.value?.contains(event.target)) panel.value = undefined;
}

onMounted(() => document.addEventListener("pointerdown", closeOutside));
onUnmounted(() => document.removeEventListener("pointerdown", closeOutside));
watch(canReadStatus, refresh, { immediate: true });
watch(() => route.fullPath, () => { panel.value = undefined; });
</script>

<template>
  <header ref="header" class="legion-header" @keydown.esc.stop="dismiss" @focusout="(event) => { if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node)) panel = undefined; }">
    <button type="button" class="admin-icon" aria-controls="legion-sidebar" :aria-expanded="expanded"
      :title="expanded ? 'Collapse sidebar' : 'Expand sidebar'" :aria-label="expanded ? 'Collapse sidebar' : 'Expand sidebar'" @click="$emit('toggle')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M9 5v14" /></svg>
    </button>
    <span class="brand">Legion Admin</span>
    <h1 v-if="title">{{ title }}</h1>
    <div class="header-controls">
      <button type="button" class="admin-icon" title="Notifications" aria-label="Notifications" :aria-expanded="panel === 'notifications'" @click="toggle('notifications', $event)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0" /></svg>
        <span v-if="offline?.length" class="indicator" aria-hidden="true"></span>
      </button>
      <button type="button" class="admin-icon" title="Help" aria-label="Help" :aria-expanded="panel === 'help'" @click="toggle('help', $event)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9 9a3 3 0 1 1 5 2c-1.5 1-2 1.5-2 3m0 3h.01" /></svg>
      </button>
      <button type="button" class="admin-icon profile" title="Profile" aria-label="Profile" :aria-expanded="panel === 'profile'" @click="toggle('profile', $event)">{{ initials }}</button>
    </div>
    <section v-if="panel" class="header-popover" :aria-label="panel">
      <template v-if="panel === 'notifications'">
        <strong>Notifications</strong>
        <p v-if="loading" role="status">Checking agent status…</p>
        <p v-else-if="!offline">Agent status unavailable.</p>
        <p v-else-if="!offline.length">No offline agents reported.</p>
        <RouterLink v-else :to="{ name: 'agents', query: { status: 'offline' } }" @click="panel = undefined">View {{ offline.length }} offline {{ offline.length === 1 ? 'agent' : 'agents' }}</RouterLink>
      </template>
      <template v-else-if="panel === 'help'">
        <strong>Help</strong>
        <p>Open a row to see details and edit its configuration. Agent changes apply within a few seconds. MCP server changes apply at Legion’s next start.</p>
      </template>
      <template v-else>
        <strong>{{ auth.account?.username }}</strong>
        <label>Theme
          <select :value="theme" @change="setTheme(($event.target as HTMLSelectElement).value as typeof theme)">
            <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
          </select>
        </label>
        <button type="button" class="chip" @click="auth.logout().catch(() => {})">Log out</button>
      </template>
    </section>
  </header>
</template>

<style scoped>
.legion-header { position: relative; z-index: 2; display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 4px 10px; border-bottom: 1px solid var(--border); background: var(--bg); }
.brand { flex: none; color: var(--accent); font-weight: 700; font-size: 0.88rem; }
h1 { min-width: 0; padding-inline-start: 10px; border-inline-start: 1px solid var(--border); margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.88rem; font-weight: 600; }
.header-controls { display: flex; gap: 4px; margin-inline-start: auto; }
.profile { background: var(--surface); font-size: 0.8rem; font-weight: 650; color: var(--text); }
.indicator { position: absolute; inset: 5px 5px auto auto; width: 6px; height: 6px; border-radius: var(--radius-full); background: var(--warning); }
.header-popover { position: absolute; inset: calc(100% + 4px) 8px auto auto; display: grid; gap: 10px; width: min(265px, calc(100vw - 16px)); padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); overflow-wrap: anywhere; }
.header-popover p { margin: 0; color: var(--muted); }
.header-popover label { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.header-popover select { min-height: 36px; }
@media (max-width: 767px) {
  .legion-header { padding-inline: 4px; gap: 4px; }
  h1 { padding-inline-start: 4px; }
  .header-controls { gap: 0; }
}
</style>
