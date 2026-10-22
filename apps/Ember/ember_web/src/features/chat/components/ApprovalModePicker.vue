<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, useTemplateRef } from "vue";
import { ALLOW_ALL_CONFIRM, APPROVAL_MODES, approvalLabel, type ApprovalMode } from "../utils/approvalMode";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";

/** The chat bar's tool-approval chip: shows how the agent asks before a tool runs and opens a small
 * menu to change it (Ask every time, Auto, Allow all). While an administrator requires approval for
 * every tool the mode is locked to "Ask every time" and the other two are disabled. "Allow all" asks
 * for a confirmation first. The menu opens upward, since the bar is at the bottom of the page. */

const props = defineProps<{
  mode: ApprovalMode;
  /** An administrator requires approval before every tool: not changeable. */
  forced: boolean;
}>();
const emit = defineEmits<{ "update:mode": [mode: ApprovalMode] }>();

const menuId = useId();
const open = ref(false);
const confirming = ref(false);
const root = useTemplateRef<HTMLElement>("root");
const chip = useTemplateRef<HTMLButtonElement>("chip");
const items = useTemplateRef<HTMLButtonElement[]>("items");

// What is in force: an administrator's requirement shows as "Ask every time".
const shown = () => (props.forced ? "ask" : props.mode);
const locked = (id: ApprovalMode) => props.forced && id !== "ask";

async function openMenu(): Promise<void> {
  open.value = true;
  await nextTick();
  const current = APPROVAL_MODES.findIndex((m) => m.id === shown());
  items.value?.[Math.max(current, 0)]?.focus();
}

async function closeMenu(returnFocus = true): Promise<void> {
  open.value = false;
  if (returnFocus) {
    await nextTick();
    chip.value?.focus();
  }
}

function choose(id: ApprovalMode): void {
  if (locked(id)) return;
  if (id === shown()) {
    void closeMenu();
    return;
  }
  if (id === "allow_all") {
    // Nothing asks any more: say so first. The menu goes away behind the dialog.
    open.value = false;
    confirming.value = true;
    return;
  }
  emit("update:mode", id);
  void closeMenu();
}

function confirmAll(): void {
  confirming.value = false;
  emit("update:mode", "allow_all");
  void nextTick(() => chip.value?.focus());
}

function move(step: number): void {
  const list = items.value ?? [];
  const at = list.findIndex((el) => el === document.activeElement);
  list[(at + step + list.length) % list.length]?.focus();
}

function onMenuKey(event: KeyboardEvent): void {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    move(1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    move(-1);
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    void closeMenu();
  } else if (event.key === "Tab") {
    void closeMenu(false);
  } else if (/^[1-3]$/.test(event.key)) {
    event.preventDefault();
    const mode = APPROVAL_MODES[Number(event.key) - 1];
    if (mode) choose(mode.id);
  }
}

function onDocumentClick(event: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false;
}
onMounted(() => document.addEventListener("click", onDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocumentClick));
</script>

<template>
  <div ref="root" class="approval-picker">
    <button
      ref="chip"
      type="button"
      class="mode-chip"
      aria-haspopup="menu"
      :aria-expanded="open"
      :aria-controls="open ? menuId : undefined"
      :title="forced ? 'Your administrator requires approval before every tool' : 'Choose when the agent asks before running a tool'"
      @click="open ? closeMenu(false) : openMenu()"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" class="icon">
        <path d="M12 3 5 6v5c0 4.5 3 8.2 7 10 4-1.8 7-5.5 7-10V6l-7-3Z" />
        <path v-if="shown() !== 'allow_all'" d="m9 12 2 2 4-4" />
      </svg>
      <span class="label">{{ approvalLabel(shown()) }}</span>
      <svg viewBox="0 0 24 24" aria-hidden="true" class="lock-icon"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
    </button>

    <div v-if="open" :id="menuId" class="menu" role="menu" aria-label="Tool approval" @keydown="onMenuKey">
      <button
        v-for="(m, i) in APPROVAL_MODES"
        :key="m.id"
        ref="items"
        type="button"
        role="menuitemradio"
        class="item"
        :aria-checked="m.id === shown()"
        :aria-disabled="locked(m.id)"
        :class="{ active: m.id === shown(), locked: locked(m.id) }"
        @click="choose(m.id)"
      >
        <span class="head">
          <span class="name">{{ m.label }}</span>
          <span v-if="m.id === shown()" class="check" aria-hidden="true">✓</span>
          <svg v-else-if="locked(m.id)" viewBox="0 0 24 24" aria-hidden="true" class="lock-icon check"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
          <kbd aria-hidden="true">{{ i + 1 }}</kbd>
        </span>
        <span class="desc">{{ m.description }}</span>
      </button>
      <p v-if="forced" class="forced-note">Your administrator requires approval before every tool.</p>
    </div>

    <ConfirmModal
      :open="confirming"
      :title="ALLOW_ALL_CONFIRM.title"
      :message="ALLOW_ALL_CONFIRM.message"
      :confirm-label="ALLOW_ALL_CONFIRM.confirmLabel"
      danger
      @confirm="confirmAll"
      @close="confirming = false"
    />
  </div>
</template>

<style scoped>
.approval-picker {
  position: relative;
  z-index: 15;
}
.mode-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  color: var(--muted);
  background: var(--surface);
  font: inherit;
  font-size: 0.8em;
  cursor: pointer;
}
.mode-chip:hover,
.mode-chip[aria-expanded="true"] {
  color: var(--text);
  border-color: var(--accent);
}
.icon {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.lock-icon {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  z-index: 16;
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 280px;
  max-width: calc(100vw - 32px);
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
}
.item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius-md);
  color: var(--text);
  background: none;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.item:hover:not(.locked),
.item:focus-visible {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  outline: none;
}
.item.active {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  box-shadow: inset 3px 0 var(--accent);
}
.item.locked {
  opacity: 0.55;
  cursor: not-allowed;
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.name {
  flex: 1;
  font-weight: 600;
  font-size: 0.95em;
}
.check {
  color: var(--accent);
  font-size: 0.9em;
}
kbd {
  min-width: 1.4em;
  padding: 0 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--muted);
  font: inherit;
  font-size: 0.75em;
  text-align: center;
}
.desc {
  color: var(--muted);
  font-size: 0.82em;
}
.forced-note {
  margin: 4px 10px 6px;
  color: var(--muted);
  font-size: 0.78em;
}
</style>
