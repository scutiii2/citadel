<script setup lang="ts">
import type { ForgeGroup } from "../api/ForgeClient";

defineProps<{ groups: ForgeGroup[]; selectedId: number | null }>();
const emit = defineEmits<{ select: [id: number]; create: [] }>();
</script>

<template>
  <nav class="groups" aria-label="Forge groups">
    <button type="button" class="new" @click="emit('create')">New group</button>
    <ul v-if="groups.length">
      <li v-for="g in groups" :key="g.id">
        <button
          type="button"
          class="group"
          :class="{ current: g.id === selectedId }"
          :aria-current="g.id === selectedId ? 'true' : undefined"
          @click="emit('select', g.id)"
        >
          <span class="title">{{ g.title }}</span>
          <span class="meta">
            <template v-if="g.running">
              <svg class="spinner" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" /></svg>
              Working
            </template>
            <template v-else>{{ g.members.length }} {{ g.members.length === 1 ? "worker" : "workers" }}</template>
          </span>
        </button>
      </li>
    </ul>
    <p v-else class="empty">No groups yet.</p>
  </nav>
</template>

<style scoped>
.groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}
button.new {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-contrast);
  border-radius: var(--radius-full);
  padding: 8px 14px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button.group {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  font: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease;
}
button.group:hover {
  border-color: var(--accent);
}
button.group.current {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, var(--bg));
}
.title {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 0.85em;
}
.spinner {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2.4;
  stroke-linecap: round;
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.empty {
  margin: 0;
  color: var(--muted);
  font-size: 0.9em;
}
</style>
