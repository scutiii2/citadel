<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

/** The helper icon in a panel header: one click shows a popover (in the top layer, so it also shows over a drawer) saying what the panel is for.
 * The popover is teleported to <body> because panel cards clip their paint. It closes on Escape
 * (focus returns to the icon), on a press outside, and on scroll or resize. */
const props = defineProps<{ title: string }>();

const open = ref(false);
const button = ref<HTMLButtonElement | null>(null);
const pop = ref<HTMLElement | null>(null);
const place = ref({ top: "0px", left: "0px" });
const id = `panel-help-${Math.random().toString(36).slice(2, 8)}`;

function position() {
  const rect = button.value?.getBoundingClientRect();
  if (!rect) return;
  const width = Math.min(300, window.innerWidth - 16);
  const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8);
  place.value = { top: `${rect.bottom + 6}px`, left: `${left}px` };
}

function close(returnFocus = false) {
  open.value = false;
  if (returnFocus) button.value?.focus();
}

function outside(event: Event) {
  const target = event.target as Node;
  if (!pop.value?.contains(target) && !button.value?.contains(target)) close();
}

function onScroll() { close(); }

function key(event: Event) {
  if ((event as KeyboardEvent).key === "Escape") { event.stopPropagation(); close(true); }
}

watch(open, async (now) => {
  const act = now ? "addEventListener" : "removeEventListener";
  document[act]("pointerdown", outside, true);
  document[act]("keydown", key, true);
  window[act]("resize", position);
  window[act]("scroll", onScroll, true);
  if (now) { position(); await nextTick(); pop.value?.showPopover?.(); position(); }
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", outside, true);
  document.removeEventListener("keydown", key, true);
  window.removeEventListener("resize", position);
  window.removeEventListener("scroll", onScroll, true);
});
</script>

<template>
  <button ref="button" type="button" class="admin-icon" :aria-label="`About ${props.title}`" :title="`About ${props.title}`" aria-haspopup="true" :aria-expanded="open" :aria-controls="open ? id : undefined" data-test="panel-help" @click="open = !open">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9.5 9.2a2.6 2.6 0 1 1 3.7 2.4c-.8.4-1.2 1-1.2 1.9M12 17h.01" /></svg>
  </button>
  <Teleport to="body">
    <div v-if="open" :id="id" ref="pop" popover="manual" class="panel-help" role="note" :aria-label="`About ${props.title}`" :style="place">
      <h3>{{ props.title }}</h3>
      <div class="panel-help-body"><slot /></div>
    </div>
  </Teleport>
</template>

<style>
.panel-help { position: fixed; inset: auto; margin: 0; z-index: 60; width: min(300px, calc(100vw - 16px)); max-height: 70dvh; overflow: auto; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); color: var(--text); overflow-wrap: anywhere; }
.panel-help h3 { margin: 0 0 6px; font-size: 0.9rem; }
.panel-help-body { display: grid; gap: 8px; color: var(--muted); font-size: 0.86rem; line-height: 1.45; }
.panel-help-body p { margin: 0; }
.panel-help-body code { font-family: var(--mono); }
</style>
