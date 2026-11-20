<script setup lang="ts">
import { computed, ref, useId } from "vue";
import type { StackItem, StackView } from "../api/StackClient";
import StateMessage from "../../../components/ui/status/StateMessage.vue";

/** A chat's short-term memory: how full it is, the items (pin, remove), Compact, and a field to add one.
 * Presentation only: the parent owns the data and the server calls. A change shows only after the server answered. */
const props = defineProps<{
  status: "loading" | "ready" | "missing" | "error";
  view: StackView | null;
  error: string;
  addError: string;
  pending: boolean;
  compacting: boolean;
  notice: string;
  /** An answer is being written: compacting now would race the turn's own compaction. */
  locked: boolean;
}>();

const emit = defineEmits<{
  add: [text: string];
  pin: [id: number, pinned: boolean];
  remove: [id: number];
  compact: [];
  retry: [];
}>();

const SOURCE: Record<string, string> = { user: "You", agent: "Agent", compaction: "Summary" };
const sourceLabel = (item: StackItem): string => SOURCE[item.source] ?? "";

const draft = ref("");
const fieldId = useId();
const errorId = useId();
const busy = computed(() => props.pending || props.compacting);
const canAdd = computed(() => draft.value.trim() !== "" && !busy.value);
const hasUnpinned = computed(() => !!props.view?.items.some((item) => !item.pinned));
const canCompact = computed(() => hasUnpinned.value && !busy.value && !props.locked);
const percent = computed(() => (props.view && props.view.limit > 0 ? Math.min(100, Math.round((props.view.used / props.view.limit) * 100)) : 0));

function submit(): void {
  const text = draft.value.trim();
  if (text && !busy.value) emit("add", text);
}

function onEnter(event: KeyboardEvent): void {
  if (event.shiftKey || event.isComposing) return; // a newline, or an input method still choosing
  event.preventDefault();
  submit();
}

defineExpose({ clearDraft: (): void => { draft.value = ""; } });
</script>

<template>
  <div class="stack-panel" role="dialog" aria-label="Short-term memory" data-test="stack-panel">
    <StateMessage v-if="status === 'loading' && !view" kind="loading">Loading memory</StateMessage>
    <StateMessage v-else-if="status === 'error' && !view" kind="error" @retry="emit('retry')">{{ error }}</StateMessage>
    <StateMessage v-else-if="status === 'missing'" kind="empty" title="Not saved yet">
      Send a message first. Short-term memory is kept once the chat is saved.
    </StateMessage>
    <template v-else-if="view">
      <p class="summary"><strong>{{ view.used }} of {{ view.limit }} items</strong></p>
      <div class="bar" role="progressbar" aria-label="Memory used" :aria-valuenow="view.used" aria-valuemin="0" :aria-valuemax="view.limit">
        <i :class="{ warn: view.warn, full: view.full }" :style="{ width: `${percent}%` }" />
      </div>
      <p v-if="view.full" class="status full" role="status" data-test="stack-full">
        <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        Full. Adding an item drops the oldest unpinned one.
      </p>
      <p v-else-if="view.warn" class="status warn" role="status" data-test="stack-warn">
        <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        Nearly full. It is compacted when you send your next message, or compact it now.
      </p>
      <div class="actions">
        <button
          type="button" class="pill-btn ghost" data-test="compact" :aria-busy="compacting ? 'true' : undefined"
          :disabled="!canCompact" :title="hasUnpinned ? undefined : 'Nothing to compact'" @click="emit('compact')"
        >{{ compacting ? "Compacting" : "Compact now" }}</button>
        <span v-if="compacting" class="hint">This can take a moment.</span>
        <span v-else-if="locked" class="hint">Available when the answer is done.</span>
      </div>
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="error" class="error" role="alert" data-test="stack-error">{{ error }}</p>
      <ul v-if="view.items.length" class="items">
        <li v-for="item in view.items" :key="item.id" data-test="stack-item">
          <button
            type="button" class="icon-btn" :class="{ on: item.pinned }" data-test="pin" :aria-pressed="item.pinned"
            :aria-label="item.pinned ? 'Unpin item' : 'Pin item'" :disabled="busy" @click="emit('pin', item.id, !item.pinned)"
          >
            <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M10 2l4 4-3 1-2 3-3-3 3-2zM6 10l-3 3" /></svg>
          </button>
          <span class="body">
            <span class="text">{{ item.text }}</span>
            <span class="meta">
              <span v-if="item.pinned" class="pinned">Pinned</span>
              <span v-if="sourceLabel(item)">{{ sourceLabel(item) }}</span>
            </span>
          </span>
          <button type="button" class="icon-btn" data-test="remove" aria-label="Remove item" :disabled="busy" @click="emit('remove', item.id)">
            <svg class="line-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
          </button>
        </li>
      </ul>
      <StateMessage v-else kind="empty">Nothing is remembered in this chat yet. Agents save short facts here, and you can add one.</StateMessage>
      <p v-if="view.items.length" class="note">Pinned items are never dropped when the list is full.</p>
      <form class="add" @submit.prevent="submit">
        <label :for="fieldId">Add something to remember</label>
        <textarea
          :id="fieldId" v-model="draft" :readonly="pending" rows="2" maxlength="2000" data-test="add-text"
          :aria-invalid="addError ? 'true' : undefined" :aria-describedby="addError ? errorId : undefined" @keydown.enter="onEnter"
        />
        <p v-if="addError" :id="errorId" class="error" role="alert" data-test="add-error">{{ addError }}</p>
        <button type="submit" class="pill-btn primary" :disabled="!canAdd">Add</button>
      </form>
    </template>
  </div>
</template>

<style scoped>
.stack-panel {
  box-sizing: border-box;
  width: min(360px, calc(100vw - 32px));
  max-height: 70vh;
  overflow-y: auto;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  color: var(--text);
  background: var(--surface);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--text) 18%, transparent);
  font-size: 0.9em;
}
.summary { margin: 0 0 8px; }
.bar { height: 6px; overflow: hidden; border-radius: var(--radius-full); background: var(--code-bg); }
.bar i { display: block; height: 100%; background: var(--accent); }
.bar i.warn { background: var(--warning); }
.bar i.full { background: var(--danger); }
.status { display: flex; align-items: flex-start; gap: 6px; margin: 10px 0 0; }
.status .line-icon { flex-shrink: 0; }
.status.warn .line-icon { color: var(--warning); }
.status.full .line-icon { color: var(--danger); }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0 0; }
.hint, .note, .meta { color: var(--muted); font-size: 0.9em; }
.notice { margin: 8px 0 0; }
.error { margin: 8px 0 0; color: var(--text); overflow-wrap: anywhere; }
.stack-panel :deep(.state.error) { color: var(--text); }
.items { margin: 12px 0 0; padding: 0; list-style: none; }
.items li { display: flex; align-items: flex-start; gap: 6px; padding: 6px 0; border-top: 1px solid var(--border); }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.text { overflow-wrap: anywhere; white-space: pre-wrap; }
.meta { display: flex; gap: 8px; }
.pinned { color: var(--accent); font-weight: 600; }
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
  min-width: 32px; min-height: 32px; padding: 0; border: none; border-radius: var(--radius-md);
  cursor: pointer; background: transparent; color: var(--muted);
}
.icon-btn:hover:not(:disabled) { background: var(--code-bg); color: var(--text); }
.icon-btn.on { color: var(--accent); }
.icon-btn:disabled { cursor: default; opacity: 0.5; }
.note { margin: 8px 0 0; }
.add { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin-top: 14px; }
.add label { font-weight: 600; }
.add textarea {
  box-sizing: border-box; width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--bg); color: var(--text); font: inherit; resize: vertical;
}
.add textarea:focus { border-color: var(--accent); }
.add textarea[aria-invalid="true"] { border-color: var(--danger); }
@media (max-width: 767px) {
  .icon-btn, .pill-btn, :deep(button.chip) { min-width: 44px; min-height: 44px; }
}
</style>
