<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { PermissionItem, TranscriptItem } from "../utils/forgeTranscript";
import MarkdownContent from "./MarkdownContent.vue";

const props = defineProps<{ items: TranscriptItem[]; running: boolean }>();
const emit = defineEmits<{ answer: [requestId: string, allow: boolean] }>();

const scroller = ref<HTMLElement | null>(null);
// Follow new text only while the reader is at the bottom; scrolling up pauses it.
let stick = true;

function onScroll(): void {
  const el = scroller.value;
  if (el) stick = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}

watch(
  () => [props.items.length, props.items.at(-1)?.kind === "worker" ? (props.items.at(-1) as { text: string }).text.length : 0],
  async () => {
    if (!stick) return;
    await nextTick();
    const el = scroller.value;
    if (el) el.scrollTop = el.scrollHeight;
  },
);

const STATUS_TEXT: Record<Exclude<PermissionItem["status"], "pending">, string> = {
  allowed: "Allowed",
  denied: "Denied",
  timed_out: "No answer, so it was denied",
};

function time(iso: string | null): string {
  return iso ? new Date(`${iso}Z`).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
}
</script>

<template>
  <div ref="scroller" class="transcript" role="log" aria-live="polite" :aria-busy="running" @scroll="onScroll">
    <p v-if="!items.length" class="empty">Start with @ to pick a worker, for example @claude look at the failing test.</p>

    <template v-for="item in items" :key="item.key">
      <article v-if="item.kind === 'user'" class="user">
        <p>{{ item.text }}</p>
        <time>{{ time(item.time) }}</time>
      </article>

      <article v-else-if="item.kind === 'worker'" class="worker" :class="{ partial: item.partial }">
        <header>
          <strong class="who">@{{ item.label }}</strong>
          <span v-if="item.streaming" class="note">Writing…</span>
          <span v-else-if="item.partial" class="note">Partial answer</span>
          <time>{{ time(item.time) }}</time>
        </header>
        <MarkdownContent :text="item.text" />
        <footer v-if="item.usage" class="usage">{{ item.usage.input_tokens }} in · {{ item.usage.output_tokens }} out</footer>
      </article>

      <div v-else-if="item.kind === 'tool'" class="tool">
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M14.7 6.3a4 4 0 0 0-5 5L3 18v3h3l6.7-6.7a4 4 0 0 0 5-5l-2.4 2.4-2.6-.6-.6-2.6z" /></svg>
        <span class="who">@{{ item.label }}</span>
        <code>{{ item.name }}</code>
        <span class="summary">{{ item.summary }}</span>
      </div>

      <div v-else-if="item.kind === 'permission'" class="permission" :class="item.status">
        <div class="ask">
          <strong class="who">@{{ item.label }}</strong> wants to use <code>{{ item.tool }}</code>
          <pre v-if="item.summary">{{ item.summary }}</pre>
        </div>
        <div v-if="item.status === 'pending'" class="buttons">
          <button type="button" class="allow" @click="emit('answer', item.requestId, true)">Allow</button>
          <button type="button" class="deny" @click="emit('answer', item.requestId, false)">Deny</button>
        </div>
        <p v-else class="result">
          <svg v-if="item.status === 'allowed'" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5" /></svg>
          <svg v-else viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          {{ STATUS_TEXT[item.status] }}
        </p>
      </div>

      <p v-else class="system">{{ item.text }}</p>
    </template>
  </div>
</template>

<style scoped>
.transcript {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
}
.empty,
.system {
  margin: 0;
  color: var(--muted);
  font-size: 0.9em;
  overflow-wrap: anywhere;
}
.system {
  text-align: center;
}
article {
  max-width: min(720px, 100%);
  border-radius: var(--radius-lg);
  padding: 8px 12px;
}
article p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.user {
  align-self: flex-end;
  background: var(--user-bubble);
}
.worker {
  align-self: flex-start;
  border: 1px solid var(--border);
  background: var(--surface);
}
.worker.partial {
  border-style: dashed;
}
header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}
.who {
  color: var(--accent);
}
.note,
time,
.usage {
  color: var(--muted);
  font-size: 0.8em;
}
time {
  margin-left: auto;
}
.user time {
  display: block;
  text-align: right;
}
.tool {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: var(--muted);
  font-size: 0.85em;
}
.tool svg,
.result svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.tool code,
.permission code {
  background: var(--code-bg);
  border-radius: var(--radius-sm);
  padding: 1px 6px;
  font-family: var(--mono);
}
.summary {
  font-family: var(--mono);
  overflow-wrap: anywhere;
}
.permission {
  border: 1px solid var(--warning);
  border-radius: var(--radius-lg);
  padding: 10px 12px;
  background: color-mix(in srgb, var(--warning) 8%, var(--bg));
}
.permission.allowed,
.permission.denied,
.permission.timed_out {
  border-color: var(--border);
  background: var(--surface);
}
.permission pre {
  margin: 6px 0 0;
  padding: 6px 8px;
  background: var(--code-bg);
  border-radius: var(--radius-md);
  font-family: var(--mono);
  font-size: 0.85em;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.buttons {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.buttons button {
  border-radius: var(--radius-full);
  padding: 6px 16px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button.allow {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-contrast);
}
button.deny {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
}
.result {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 0.9em;
}
</style>
