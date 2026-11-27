<script setup lang="ts">
// The header's usage ring: it shows the fuller of the account's token limits and opens the numbers.
// Not a modal: it closes on Esc, a press outside or a page change.
import { computed, onMounted, ref, useId, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { ProgressRing } from "@citadel/ui";
import { resetText, useUsageLimitsStore } from "../stores/usageLimits";
import UsageResets from "./UsageResets.vue";
import { useAuthStore } from "../../../stores/auth";
import { useOutsideClose } from "../../../composables/useOutsideClose";

defineProps<{
  /** The account may open the Usage page. */
  detailsLink?: boolean;
}>();

const ALMOST = 90;
const store = useUsageLimitsStore();
const auth = useAuthStore();
const route = useRoute();
const open = ref(false);
const root = ref<HTMLElement | null>(null);
const trigger = ref<HTMLButtonElement | null>(null);
const panelId = useId();

const percent = computed(() => Math.max(0, ...store.windows.map((w) => w.percent)));
const almost = computed(() => percent.value >= ALMOST);
const hasResets = computed(() => (store.usage?.resets?.length ?? 0) > 0);
const label = computed(() => {
  if (!store.windows.length) return "Usage limits: none set, free resets available";
  const parts = store.windows.map((w) => `${w.title.toLowerCase()} ${w.percent}%`);
  return `Usage limits: ${parts.join(", ")}${almost.value ? ", almost used up" : ""}`;
});

function toggle(): void {
  open.value = !open.value;
  if (open.value) void store.load();
}

function close(refocus = false): void {
  open.value = false;
  if (refocus) trigger.value?.focus();
}

/** Escape closes the panel, except from a question inside it, which answers the key itself. */
function onEscape(event: KeyboardEvent): void {
  if ((event.target as Element).closest("dialog")) return;
  event.preventDefault();
  event.stopPropagation();
  close(true);
}

onMounted(() => void store.load());
watch(() => auth.account?.id, () => {
  close();
  void store.load();
});
watch(() => route.fullPath, () => {
  close();
  void store.load();
});
useOutsideClose(root, open, () => close());
</script>

<template>
  <div v-if="store.windows.length || hasResets" ref="root" class="usage-meter" @keydown.esc="onEscape">
    <button
      ref="trigger"
      type="button"
      class="meter"
      :title="label"
      :aria-label="label"
      :aria-expanded="open"
      :aria-controls="open ? panelId : undefined"
      @click="toggle"
    >
      <ProgressRing :percent="percent" :danger="almost" />
    </button>

    <section v-if="open" :id="panelId" class="panel" aria-label="Usage limits">
      <h2>Usage limits</h2>
      <div v-for="w in store.windows" :key="w.key" class="limit">
        <p class="head"><span>{{ w.title }}</span><span>{{ w.percent }}%</span></p>
        <div class="bar" role="progressbar" :aria-label="w.title" :aria-valuenow="w.percent" aria-valuemin="0" aria-valuemax="100">
          <span :class="{ full: w.percent >= ALMOST }" :style="{ width: `${w.percent}%` }" />
        </div>
        <p class="note">{{ w.window.used.toLocaleString() }} of {{ w.window.limit.toLocaleString() }} tokens</p>
        <p v-if="resetText(w)" class="note">{{ resetText(w) }}</p>
      </div>
      <p class="note">{{ store.windows.length ? "An administrator sets these limits." : "No limit is set." }}</p>
      <UsageResets />
      <RouterLink v-if="detailsLink" to="/usage" class="details" @click="close()">Usage details</RouterLink>
    </section>
  </div>
</template>

<style scoped>
.usage-meter {
  position: relative;
}
.meter {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  background: transparent;
}
.meter:hover,
.meter[aria-expanded="true"] {
  background: var(--surface);
}
.panel {
  position: absolute;
  z-index: 40;
  top: calc(100% + 6px);
  right: 0;
  display: grid;
  gap: 10px;
  width: 280px;
  max-height: calc(100dvh - 72px);
  overflow-y: auto;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 6px 24px rgb(0 0 0 / 22%);
}
h2 {
  margin: 0;
  font-size: 0.88rem;
}
.panel :deep(.resets) {
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.panel :deep(.resets h3) {
  font-size: 0.85rem;
}
.head {
  display: flex;
  justify-content: space-between;
  margin: 0 0 4px;
  font-size: 0.8rem;
}
.bar {
  height: 6px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--code-bg);
}
.bar span {
  display: block;
  height: 100%;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.bar span.full {
  background: var(--danger);
}
.note {
  margin: 4px 0 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.details {
  justify-self: start;
  font-size: 0.8rem;
  color: var(--accent);
}
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
