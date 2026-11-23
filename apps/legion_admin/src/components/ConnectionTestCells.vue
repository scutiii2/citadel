<script setup lang="ts">
import { computed, ref, useId } from "vue";
import type { ConnectionTestResult } from "../api/AgentsAdminClient";
import { errorMessage } from "../utils/errors";

/**
 * Two table cells for one row: the Test button and its Result. The result is an icon only; a failure adds its code,
 * and hovering or focusing the icon opens a popover saying what it means. A test only reads and never shows a token.
 */
const props = defineProps<{ label: string; run: () => Promise<ConnectionTestResult> }>();
const testing = ref(false);
const outcome = ref<{ ok: boolean; code: string; lines: { ok: boolean; text: string; code?: string }[] } | null>(null);
const popoverId = useId();
const anchor = ref<HTMLElement>();
const popover = ref<HTMLElement>();

const summary = computed(() => (outcome.value ? (outcome.value.ok ? "Connected" : `Failed, code ${outcome.value.code}`) : "Not tested"));

async function test() {
  if (testing.value) return;
  testing.value = true;
  outcome.value = null;
  try {
    const result = await props.run();
    const origins = result.origins ?? [];
    outcome.value = {
      ok: result.ok,
      code: result.code ?? (result.ok ? "" : "ERR"),
      lines: origins.length > 1
        ? [{ ok: result.ok, text: result.message }, ...origins.map((origin, index) => ({ ok: origin.ok, text: `Address ${index + 1}: ${origin.message}`, code: origin.code }))]
        : [{ ok: result.ok, text: result.message }],
    };
  } catch (err) {
    // The request itself failed (Legion or Portcullis did not answer).
    outcome.value = { ok: false, code: "ERR", lines: [{ ok: false, text: errorMessage(err) }] };
  } finally {
    testing.value = false;
  }
}

function show() {
  const bubble = popover.value;
  const origin = anchor.value;
  if (!bubble || !origin || !outcome.value) return;
  bubble.showPopover?.();
  const box = origin.getBoundingClientRect();
  const width = bubble.offsetWidth || 260;
  bubble.style.top = `${box.bottom + 8}px`;
  bubble.style.left = `${Math.max(8, Math.min(box.left + box.width / 2 - width / 2, window.innerWidth - width - 8))}px`;
}

function hide() {
  popover.value?.hidePopover?.();
}
</script>

<template>
  <td class="test-cell">
    <button type="button" class="admin-icon test-button" :class="{ running: testing }" data-test="test" :aria-label="`Test ${label}`"
      :title="`Test ${label}`" :disabled="testing" :aria-busy="testing" @click="test">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path class="beat" d="M3 12h4l2.5-6 4 12 2.5-6H21" /></svg>
    </button>
  </td>
  <td class="result-cell" aria-live="polite">
    <span v-if="testing" class="spinner" role="status" aria-label="Testing" data-test="testing">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /></svg>
    </span>
    <span v-else-if="outcome" ref="anchor" class="result" :class="outcome.ok ? 'ok' : 'bad'" tabindex="0" role="img" data-test="test-result"
      :aria-label="summary" :aria-describedby="popoverId" @mouseenter="show" @mouseleave="hide" @focus="show" @blur="hide">
      <svg v-if="outcome.ok" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.7 2.7L16 9.8" /></svg>
      <template v-else>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9 9l6 6M15 9l-6 6" /></svg>
        <code class="code" data-test="test-code">{{ outcome.code }}</code>
      </template>
    </span>
    <span v-else class="idle" aria-label="Not tested">–</span>
    <div v-if="outcome" :id="popoverId" ref="popover" popover="manual" role="tooltip" class="test-popover" data-test="test-popover">
      <p v-for="(line, index) in outcome.lines" :key="index" :class="line.ok ? 'ok' : 'bad'">
        <code v-if="!line.ok && (line.code || index === 0)">{{ line.code ?? outcome.code }}</code> {{ line.text }}
      </p>
    </div>
  </td>
</template>

<style scoped>
.test-cell, .result-cell { vertical-align: middle; }
.test-button svg { fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.test-button.running { color: var(--accent); animation: test-press 900ms ease-in-out infinite; }
.test-button.running .beat { stroke-dasharray: 8 6; animation: test-beat 700ms linear infinite; }
@keyframes test-press { 50% { transform: scale(0.92); } }
@keyframes test-beat { to { stroke-dashoffset: -28; } }
.result { display: inline-flex; align-items: center; gap: 6px; border-radius: var(--radius-sm); cursor: help; animation: test-in 260ms ease-out; }
.result svg, .spinner svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.result.ok { color: var(--success); }
.result.bad { color: var(--danger); }
.code { padding: 1px 6px; border: 1px solid currentColor; border-radius: var(--radius-sm); font-size: 0.8rem; font-weight: 600; }
.spinner { display: inline-flex; color: var(--muted); }
.spinner svg { stroke-dasharray: 30 22; animation: test-spin 800ms linear infinite; }
@keyframes test-spin { to { transform: rotate(360deg); } }
@keyframes test-in { from { opacity: 0; transform: scale(0.6); } }
.idle { color: var(--muted); }
.test-popover { position: fixed; inset: auto; margin: 0; max-width: min(320px, calc(100vw - 16px)); padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); box-shadow: 0 8px 24px rgb(0 0 0 / 0.35); font-size: 0.85rem; pointer-events: none; }
.test-popover p { margin: 0; }
.test-popover p + p { margin-top: 4px; }
.test-popover .bad code { color: var(--danger); }
</style>
