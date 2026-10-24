<script setup lang="ts">
import { computed } from "vue";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import type { CalendarEvent } from "../api/CalendarClient";
import { findTeamsLink, linkify, splitDescription } from "../utils/eventDetails";

const props = defineProps<{ event: CalendarEvent | null }>();
const emit = defineEmits<{ close: [] }>();

const when = computed(() => {
  const e = props.event;
  if (!e) return "";
  const start = new Date(e.start);
  if (e.all_day) return start.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }) + " · All day";
  const end = new Date(e.end);
  const day = start.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  const time = { hour: "numeric", minute: "2-digit" } as const;
  return `${day} · ${start.toLocaleTimeString(undefined, time)} – ${end.toLocaleTimeString(undefined, time)}`;
});
const parts = computed(() => splitDescription(props.event?.description ?? ""));
const join = computed(() => (props.event ? findTeamsLink(props.event.description, props.event.location) : null));
</script>

<template>
  <BaseModal :open="event !== null" :title="event?.title ?? ''" @close="emit('close')">
    <div v-if="event" class="details">
      <p class="sources">
        <span v-for="s in event.sources" :key="s.name" class="badge"><i class="dot" :style="{ background: s.color }" />{{ s.name }}</span>
      </p>
      <p class="when">{{ when }}</p>
      <p v-if="event.location" class="where">
        <template v-for="(part, i) in linkify(event.location)" :key="i">
          <a v-if="'href' in part" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.label }}</a>
          <template v-else>{{ part.text }}</template>
        </template>
      </p>
      <a v-if="join" class="join" :href="join" target="_blank" rel="noopener noreferrer">Join Teams meeting</a>
      <pre class="description"><template v-for="(part, i) in linkify(parts.description || 'No additional description.')" :key="i"><a v-if="'href' in part" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.label }}</a><template v-else>{{ part.text }}</template></template></pre>
      <details v-if="parts.footer" class="footer">
        <summary>Meeting information &amp; original details</summary>
        <pre><template v-for="(part, i) in linkify(parts.footer)" :key="i"><a v-if="'href' in part" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.label }}</a><template v-else>{{ part.text }}</template></template></pre>
      </details>
    </div>
  </BaseModal>
</template>

<style scoped>
.details { display: grid; gap: 12px; min-width: 0; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 0.8rem; }
.dot { width: 10px; height: 10px; border-radius: var(--radius-full); }
.when, .where { margin: 0; overflow-wrap: anywhere; }
.when { font-weight: 600; }
.join { justify-self: start; padding: 10px 18px; color: var(--accent-contrast); background: var(--accent); border-radius: var(--radius-md); font-weight: 600; text-decoration: none; }
pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; color: var(--muted); max-height: 40vh; overflow: auto; }
a { color: var(--accent); }
.footer summary { cursor: pointer; font-weight: 600; }
</style>
