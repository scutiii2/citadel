<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { FORGE_MESSAGE_MAX } from "../api/ForgeClient";
import { completeMention, matchingLabels, mentionAt } from "../utils/forgeMention";

const props = defineProps<{
  /** The @handles of the group's workers. */
  labels: string[];
  running: boolean;
  busy: boolean;
  /** Non-empty: why nothing can be sent (no worker invited yet). */
  disabledReason: string;
  error: string;
}>();
const text = defineModel<string>({ required: true });
const emit = defineEmits<{ send: []; stop: [] }>();

const field = ref<HTMLTextAreaElement | null>(null);
const caret = ref(0);
const active = ref(0);
const dismissed = ref(false);

const mention = computed(() => mentionAt(text.value, caret.value));
const options = computed(() => (mention.value ? matchingLabels(props.labels, mention.value.query) : []));
const menuOpen = computed(() => options.value.length > 0 && !dismissed.value);
const blank = computed(() => text.value.trim() === "");
const canSend = computed(() => !blank.value && !props.busy && !props.running && props.disabledReason === "");
const nearLimit = computed(() => text.value.length > FORGE_MESSAGE_MAX * 0.9);

watch(text, () => {
  dismissed.value = false;
  active.value = 0;
});

function track(): void {
  caret.value = field.value?.selectionStart ?? text.value.length;
}

function pick(label: string): void {
  const current = mention.value;
  if (!current) return;
  const done = completeMention(text.value, current, caret.value, label);
  text.value = done.text;
  void nextTick(() => {
    field.value?.focus();
    field.value?.setSelectionRange(done.caret, done.caret);
    caret.value = done.caret;
  });
}

function onKey(event: KeyboardEvent): void {
  if (menuOpen.value) {
    const count = options.value.length;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      active.value = (active.value + 1) % count;
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      active.value = (active.value - 1 + count) % count;
      return;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      pick(options.value[active.value]!);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      dismissed.value = true;
      return;
    }
  }
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (canSend.value) emit("send");
  }
}
</script>

<template>
  <form class="composer" @submit.prevent="canSend && emit('send')">
    <p v-if="disabledReason" class="reason">{{ disabledReason }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="row">
      <div class="field">
        <ul v-if="menuOpen" class="menu" role="listbox" aria-label="Workers">
          <li
            v-for="(label, index) in options"
            :key="label"
            role="option"
            :aria-selected="index === active"
            :class="{ active: index === active }"
            @mousedown.prevent="pick(label)"
          >
            @{{ label }}
          </li>
        </ul>
        <textarea
          ref="field"
          v-model="text"
          rows="2"
          :maxlength="FORGE_MESSAGE_MAX"
          :disabled="disabledReason !== ''"
          aria-label="Message"
          placeholder="Write to a worker with @name. Enter sends, Shift+Enter adds a line."
          @keydown="onKey"
          @input="track"
          @keyup="track"
          @click="track"
        />
        <span v-if="nearLimit" class="count">{{ text.length }}/{{ FORGE_MESSAGE_MAX }}</span>
      </div>
      <button v-if="running" type="button" class="stop" @click="emit('stop')">Stop</button>
      <button v-else type="submit" class="send" :disabled="!canSend" :aria-busy="busy">Send</button>
    </div>
  </form>
</template>

<style scoped>
.composer {
  border-top: 1px solid var(--border);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.field {
  position: relative;
  flex: 1;
  min-width: 0;
}
textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  max-height: 40vh;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
}
textarea:focus {
  border-color: var(--accent);
}
.menu {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 0;
  margin: 0;
  padding: 4px;
  list-style: none;
  min-width: 160px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  z-index: 2;
}
.menu li {
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.menu li.active {
  background: color-mix(in srgb, var(--accent) 14%, var(--bg));
}
.count {
  position: absolute;
  right: 8px;
  bottom: 6px;
  color: var(--muted);
  font-size: 0.8em;
}
button.send,
button.stop {
  border-radius: var(--radius-full);
  padding: 8px 18px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button.send {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-contrast);
}
button.send:disabled {
  opacity: 0.5;
  cursor: default;
}
button.stop {
  border: 1px solid var(--danger);
  background: transparent;
  color: var(--danger);
}
.reason {
  margin: 0;
  color: var(--muted);
  font-size: 0.9em;
}
.error {
  margin: 0;
  color: var(--danger);
  font-size: 0.9em;
}
</style>
