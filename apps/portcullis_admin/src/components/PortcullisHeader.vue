<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import AccountMenu from "./AccountMenu.vue";

/** The compact full-width header: sidebar toggle, identity, page title, and Notifications, Help and Profile. */
defineProps<{ title: string; expanded: boolean }>();
defineEmits<{ toggle: [] }>();
const auth = useAuthStore();
const issues = useConfigIssuesStore();
const route = useRoute();
const panel = ref<"notifications" | "help" | "profile">();
const trigger = ref<HTMLElement>();
const header = ref<HTMLElement>();
const canReadIssues = computed(() => auth.hasPermission("config.issues.view"));
const initials = computed(() => auth.account?.username.slice(0, 2).toUpperCase() ?? "");
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
/** One row per kind of problem, errors first. */
const notices = computed(() => {
  const rows = [
    { tone: "error", count: issues.errorCount, word: "error", note: "Fix these to keep Portcullis healthy." },
    { tone: "warning", count: issues.warningCount, word: "warning", note: "Worth a look; you can ignore a warning." },
  ];
  return rows.filter((r) => r.count).map((r) => ({ ...r, title: plural(r.count, r.word) }));
});

function toggle(next: typeof panel.value, event: MouseEvent) {
  panel.value = panel.value === next ? undefined : next;
  if (panel.value) trigger.value = event.currentTarget as HTMLElement;
  if (panel.value === "notifications" && canReadIssues.value) void issues.refresh();
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
watch(() => route.fullPath, () => { panel.value = undefined; });
</script>

<template>
  <header ref="header" class="portcullis-header" @keydown.esc.stop="dismiss" @focusout="(event) => { if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node)) panel = undefined; }">
    <button type="button" class="admin-icon" aria-controls="portcullis-sidebar" :aria-expanded="expanded"
      :title="expanded ? 'Collapse sidebar' : 'Expand sidebar'" :aria-label="expanded ? 'Collapse sidebar' : 'Expand sidebar'" @click="$emit('toggle')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M9 5v14" /></svg>
    </button>
    <span class="brand">Portcullis Admin</span>
    <h1 v-if="title">{{ title }}</h1>
    <div class="header-controls">
      <button type="button" class="admin-icon" title="Notifications" aria-label="Notifications" :aria-expanded="panel === 'notifications'" @click="toggle('notifications', $event)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0" /></svg>
        <span v-if="canReadIssues && issues.active.length" class="indicator" :class="{ errors: issues.errorCount > 0 }" aria-hidden="true"></span>
      </button>
      <button type="button" class="admin-icon" title="Help" aria-label="Help" :aria-expanded="panel === 'help'" @click="toggle('help', $event)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9 9a3 3 0 1 1 5 2c-1.5 1-2 1.5-2 3m0 3h.01" /></svg>
      </button>
      <button type="button" class="admin-icon profile" title="Profile" aria-label="Profile" :aria-expanded="panel === 'profile'" @click="toggle('profile', $event)">{{ initials }}</button>
    </div>
    <section v-if="panel" class="header-popover" :aria-label="panel">
      <template v-if="panel === 'notifications'">
        <div class="popover-head"><strong>Notifications</strong><span v-if="canReadIssues && issues.active.length" class="popover-count">{{ issues.active.length }}</span></div>
        <p v-if="!canReadIssues" class="popover-empty">Nothing to report for your access.</p>
        <p v-else-if="issues.loading" class="popover-empty" role="status">Checking configuration…</p>
        <p v-else-if="issues.error" class="popover-empty error" role="alert">Configuration check failed: {{ issues.error }}</p>
        <p v-else-if="!issues.active.length" class="popover-empty">You're all caught up. No config issues.</p>
        <template v-else>
          <ul class="notices" aria-label="Config issues">
            <li v-for="n in notices" :key="n.tone">
              <RouterLink to="/config-issues" class="notice" :class="n.tone" @click="panel = undefined">
                <span class="notice-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path v-if="n.tone === 'error'" d="M12 8v5m0 3h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18" /><path v-else d="M12 4 3 20h18zM12 10v4m0 3h.01" /></svg>
                </span>
                <span class="notice-text"><strong>{{ n.title }}</strong><small>{{ n.note }}</small></span>
                <svg class="notice-go" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
              </RouterLink>
            </li>
          </ul>
          <RouterLink to="/config-issues" class="popover-link" @click="panel = undefined">View all config issues</RouterLink>
        </template>
      </template>
      <template v-else-if="panel === 'help'">
        <strong>Help</strong>
        <p>Open a row to see its details and edit it in the drawer. Accounts: search by name, email or role, change roles and save. Roles: edit permissions and save to apply them to every holder. Invites: Invite member sends an email invite. Workspace settings apply to every account, and each panel saves on its own.</p>
      </template>
      <AccountMenu v-else-if="auth.account" :username="auth.account.username" :email="auth.account.email" @navigate="panel = undefined" @logout="auth.logout().catch(() => {})" />
    </section>
  </header>
</template>

<style scoped>
.portcullis-header { position: relative; z-index: 2; display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 4px 10px; border-bottom: 1px solid var(--border); background: var(--bg); }
.brand { flex: none; color: var(--accent); font-weight: 700; font-size: 0.88rem; }
h1 { min-width: 0; padding-inline-start: 10px; border-inline-start: 1px solid var(--border); margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.88rem; font-weight: 600; }
.header-controls { display: flex; gap: 4px; margin-inline-start: auto; }
.profile { background: var(--surface); font-size: 0.8rem; font-weight: 650; color: var(--text); }
.indicator { position: absolute; inset: 5px 5px auto auto; width: 6px; height: 6px; border-radius: var(--radius-full); background: var(--warning); }
.indicator.errors { background: var(--status-failed); }
.header-popover { position: absolute; inset: calc(100% + 4px) 8px auto auto; display: grid; gap: 10px; width: min(265px, calc(100vw - 16px)); max-height: 70dvh; overflow: auto; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); overflow-wrap: anywhere; }
.header-popover p { margin: 0; color: var(--muted); font-size: 0.86rem; }
.popover-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.popover-count { min-width: 22px; padding: 1px 7px; border-radius: var(--radius-full); background: var(--surface); color: var(--muted); font-size: 0.75rem; font-weight: 650; text-align: center; }
.popover-empty { padding: 10px 0 2px; text-align: center; }
.popover-empty.error { color: var(--danger); }
.notices { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.notice { display: flex; align-items: center; gap: 10px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); text-decoration: none; background: var(--surface); }
.notice:hover { border-color: color-mix(in srgb, var(--tone) 55%, var(--border)); }
.notice:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.notice.error { --tone: var(--status-failed); }
.notice.warning { --tone: var(--warning); }
.notice-icon { display: grid; flex: none; place-items: center; width: 32px; height: 32px; border-radius: var(--radius-md); color: var(--tone); background: color-mix(in srgb, var(--tone) 14%, var(--bg)); }
.notice-icon svg, .notice-go { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.notice-text { display: grid; flex: 1; min-width: 0; gap: 1px; }
.notice-text strong { font-size: 0.88rem; }
.notice-text small { color: var(--muted); font-size: 0.78rem; }
.notice-go { flex: none; color: var(--muted); }
.popover-link { justify-self: center; padding: 4px 8px; color: var(--accent); font-size: 0.84rem; }
@media (max-width: 767px) {
  .portcullis-header { padding-inline: 4px; gap: 4px; }
  h1 { padding-inline-start: 4px; }
  .header-controls { gap: 0; }
}
</style>
