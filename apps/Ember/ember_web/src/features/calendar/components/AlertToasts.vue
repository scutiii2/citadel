<script setup lang="ts">
import { useAlertPoller } from "../composables/useAlertPoller";

const { alerts, dismiss } = useAlertPoller();

function startsAt(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
</script>

<template>
  <div v-if="alerts.length" class="toasts" role="region" aria-label="Calendar alerts">
    <article v-for="alert in alerts" :key="alert.id" class="toast" role="status">
      <div class="text">
        <strong>{{ alert.title }}</strong>
        <span>Starts at {{ startsAt(alert.start_utc) }}</span>
      </div>
      <RouterLink class="open" to="/calendar" @click="dismiss(alert.id)">Open</RouterLink>
      <button type="button" class="close" :aria-label="`Dismiss alert for ${alert.title}`" @click="dismiss(alert.id)">×</button>
    </article>
  </div>
</template>

<style scoped>
.toasts { position: fixed; z-index: 40; right: 16px; bottom: calc(var(--rail-height) + 12px); display: grid; gap: 8px; max-width: min(360px, calc(100vw - 32px)); }
@media (min-width: 768px) { .toasts { bottom: 16px; } }
.toast { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 10px; padding: 12px 14px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: var(--radius-lg); }
.text { display: grid; min-width: 0; }
.text strong { overflow-wrap: anywhere; }
.text span { color: var(--muted); font-size: 0.85rem; }
.open { color: var(--accent); font-weight: 600; text-decoration: none; }
.close { min-width: 32px; min-height: 32px; color: var(--muted); background: transparent; border: 0; border-radius: var(--radius-md); font-size: 1.2rem; cursor: pointer; }
</style>
