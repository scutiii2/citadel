<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { copyText } from "../../utils/browser/clipboard";
import type { ToolRunResult } from "../../api/types";
import { formatToolResult } from "../../utils/tools/toolResultFormat";
import MarkdownContent from "../content/MarkdownContent.vue";

const props = defineProps<{ result: ToolRunResult }>();

/** Pretty-printed if the text is JSON, else null (then it renders as markdown). */
const prettyJson = computed<string | null>(() => {
  const text = props.result.text.trim();
  if (!text.startsWith("{") && !text.startsWith("[")) return null;
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return null;
  }
});

/** Readable Markdown for a JSON object result, else null. */
const formatted = computed(() => formatToolResult(props.result.text));
// Formatted by default; the raw JSON is one click away.
const showRaw = ref(false);

const copied = ref(false);
const copyFailed = ref(false);
let copyTimer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
onBeforeUnmount(() => { disposed = true; clearTimeout(copyTimer); });

async function copy(): Promise<void> {
  const ok = await copyText(prettyJson.value ?? props.result.text);
  if (disposed) return;
  clearTimeout(copyTimer);
  copied.value = ok;
  copyFailed.value = !ok;
  if (ok) copyTimer = setTimeout(() => (copied.value = false), 1500);
}
</script>

<template>
  <div :class="['result', { failed: result.isError }]">
    <div class="bar">
      <span class="status">{{ result.isError ? "Tool reported an error" : "Result" }}</span>
      <span class="buttons">
        <button v-if="formatted" type="button" class="copy" @click="showRaw = !showRaw">
          {{ showRaw ? "Formatted" : "Raw JSON" }}
        </button>
        <button type="button" class="copy" @click="copy">{{ copied ? "Copied" : copyFailed ? "Retry copy" : "Copy" }}</button>
      </span>
    </div>
    <p v-if="copyFailed" role="alert" class="error">Copy failed. Retry or select the result text to copy manually.</p>
    <p v-if="!result.text" class="muted">(no text output)</p>
    <MarkdownContent v-else-if="formatted && !showRaw" :text="formatted" />
    <pre v-else-if="prettyJson" class="json">{{ prettyJson }}</pre>
    <MarkdownContent v-else :text="result.text" />
  </div>
</template>

<style scoped>
.result {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg);
}
.result.failed {
  border-color: var(--danger);
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.status {
  font-size: 0.85em;
  font-weight: 600;
  color: var(--muted);
}
.failed .status {
  color: var(--danger);
}
.buttons {
  display: flex;
  gap: 6px;
}
.copy {
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  cursor: pointer;
  font-size: 0.85em;
  background: transparent;
}
.json {
  margin: 0;
  max-height: 420px;
  overflow: auto;
  font-family: var(--mono);
  font-size: 0.85em;
}
.muted {
  margin: 0;
  color: var(--muted);
}
</style>
