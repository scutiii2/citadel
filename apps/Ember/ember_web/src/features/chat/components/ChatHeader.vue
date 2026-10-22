<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from "vue";
import type { AgentUsage, ContextPart } from "../../../api/types";
import type { MenuItem } from "../../../components/ui/menus/menuTypes";
import type { ContextAccuracy } from "../utils/contextAccuracy";
import { useAuthStore } from "../../../stores/auth";
import ActionButton from "../../../components/ui/buttons/ActionButton.vue";
import ContextPanel from "./ContextPanel.vue";
import EntryAgentTag from "./EntryAgentTag.vue";
import PopupMenu from "../../../components/ui/menus/PopupMenu.vue";

/** The bar above a chat: its title, who it talks to, how full the agent's
 * memory is, and the actions on the chat. Export and Share are icon buttons;
 * Summarize and Clear (they change what the agent remembers) sit in a menu and
 * are off while an answer is being written (`locked`). The actions show once
 * the chat has messages. */
const props = defineProps<{
  title: string;
  hasMessages: boolean;
  /** Share of the agent's context in use, or null before an answer. */
  contextPercent: number | null;
  /** What fills the context, for the panel the meter opens; leave out (or null)
   * and the meter is plain text. */
  breakdown?: { tokens: number; window: number; parts: ContextPart[]; exact?: boolean; agentUsage?: AgentUsage[] } | null;
  /** How the next questions are counted; with it the panel shows an Estimate / Exact switch. */
  accuracy?: ContextAccuracy;
  locked: boolean;
}>();

const emit = defineEmits<{ export: []; share: []; summarize: []; clear: []; "update:accuracy": [value: ContextAccuracy] }>();

const auth = useAuthStore();

const CONTEXT_HINT = "How full the agent's memory of this chat is. At 60% the chat is summarized automatically.";
const contextTitle = computed(() =>
  props.contextPercent === null && props.breakdown ? "Prompt cost for each agent that ran this answer."
    : props.breakdown ? `How full the agent's memory of this chat is. Click for what fills it. At 60% the chat is summarized automatically.` : CONTEXT_HINT,
);

const MENU_WIDTH = 210;

// The context panel opens from the meter and closes on Esc or a press outside it.
const panelOpen = ref(false);
const contextBox = useTemplateRef<HTMLElement>("contextBox");

function closePanelOnOutside(event: PointerEvent): void {
  if (!contextBox.value?.contains(event.target as Node)) panelOpen.value = false;
}

function closePanelOnEscape(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  panelOpen.value = false;
  contextBox.value?.querySelector<HTMLElement>("button.context")?.focus();
}

watch(panelOpen, (open) => {
  if (open) {
    document.addEventListener("pointerdown", closePanelOnOutside);
    document.addEventListener("keydown", closePanelOnEscape);
  } else {
    document.removeEventListener("pointerdown", closePanelOnOutside);
    document.removeEventListener("keydown", closePanelOnEscape);
  }
});
// No breakdown any more (another chat, the setting off): nothing to show.
watch(() => props.breakdown, (breakdown) => {
  if (!breakdown) panelOpen.value = false;
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closePanelOnOutside);
  document.removeEventListener("keydown", closePanelOnEscape);
});

const menuAt = ref<{ x: number; y: number } | null>(null);
const more = useTemplateRef<InstanceType<typeof ActionButton>>("more");
const moreButton = (): HTMLElement | null => (more.value?.$el as HTMLElement | undefined) ?? null;

const items = computed<MenuItem[]>(() => [
  { id: "export", label: "Export Markdown" },
  ...(auth.hasPermission("chat.share") ? [{ id: "share", label: "Share chat" }] : []),
  { id: "summarize", label: "Summarize", disabled: props.locked },
  { id: "clear", label: "Clear", disabled: props.locked },
]);

// A press on the "..." button while the menu is open closes it: the button keeps
// its pointerdown from the menu, which would close it first and let the click reopen it.
function toggleMenu(): void {
  if (menuAt.value) {
    void closeMenu();
    return;
  }
  const box = moreButton()?.getBoundingClientRect();
  menuAt.value = { x: (box?.right ?? MENU_WIDTH) - MENU_WIDTH, y: (box?.bottom ?? 0) + 4 };
}

/** Esc, a press outside or Tab: focus goes back to the button. */
async function closeMenu(): Promise<void> {
  menuAt.value = null;
  await nextTick();
  moreButton()?.focus();
}

function choose(id: string): void {
  menuAt.value = null; // a choice opens a dialog, which takes focus
  if (id === "export") emit("export");
  else if (id === "share" && auth.hasPermission("chat.share")) emit("share");
  else if (id === "summarize") emit("summarize");
  else if (id === "clear") emit("clear");
}
</script>

<template>
  <header class="chat-header">
    <h2 class="title" :title="title">{{ title }}</h2>
    <EntryAgentTag />
    <span class="spacer" />
    <div v-if="contextPercent !== null || breakdown" ref="contextBox" class="context-box">
      <component
        :is="breakdown ? 'button' : 'span'"
        :type="breakdown ? 'button' : undefined"
        :class="['context', { high: contextPercent !== null && contextPercent >= 50 }]"
        :aria-expanded="breakdown ? panelOpen : undefined"
        :aria-haspopup="breakdown ? 'dialog' : undefined"
        :title="contextTitle"
        @click="breakdown && (panelOpen = !panelOpen)"
      >
        <template v-if="contextPercent !== null">
          Context
          <span class="meter" role="progressbar" aria-label="Context used" :aria-valuenow="contextPercent" aria-valuemin="0" aria-valuemax="100">
            <i :style="{ width: `${contextPercent}%` }" />
          </span>
          {{ contextPercent }}%
        </template>
        <template v-else>Prompt costs</template>
      </component>
      <ContextPanel
        v-if="breakdown && panelOpen"
        class="panel"
        :tokens="breakdown.tokens"
        :window="breakdown.window"
        :parts="breakdown.parts"
        :exact="breakdown.exact"
        :agent-usage="breakdown.agentUsage"
        :accuracy="accuracy"
        @update:accuracy="(value) => emit('update:accuracy', value)"
      />
    </div>
    <template v-if="hasMessages">
      <ActionButton class="desktop-action" icon="export" icon-only title="Download this chat as Markdown" @click="emit('export')">Export</ActionButton>
      <ActionButton v-if="auth.hasPermission('chat.share')" class="desktop-action" icon="share" icon-only title="Make a read-only link to this chat" @click="emit('share')">Share</ActionButton>
      <ActionButton
        ref="more"
        icon="more"
        icon-only
        class="more"
        title="More chat actions"
        aria-haspopup="menu"
        :aria-expanded="menuAt !== null"
        @pointerdown.stop
        @click.stop="toggleMenu"
      >
        More
      </ActionButton>
    </template>
    <PopupMenu v-if="menuAt" :items="items" :x="menuAt.x" :y="menuAt.y" label="Chat actions" @select="choose" @close="closeMenu" />
  </header>
</template>

<style scoped>
.chat-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
.title {
  min-width: 0;
  max-width: 40ch;
  margin: 0;
  overflow: hidden;
  font-size: 1em;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.spacer {
  flex: 1;
}
.context-box {
  position: relative;
}
.panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
}
button.context {
  padding: 2px 6px;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  background: transparent;
  font: inherit;
  font-size: 0.8em;
}
button.context:hover,
button.context[aria-expanded="true"] {
  background: var(--code-bg);
}
.context {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8em;
  color: var(--muted);
}
.context.high {
  color: var(--danger);
}
.meter {
  width: 44px;
  height: 5px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--code-bg);
}
.meter i {
  display: block;
  height: 100%;
  background: var(--accent);
}
.high .meter i {
  background: var(--danger);
}
@media (max-width: 767px) {
  .chat-header {
    gap: 4px 8px;
    padding: 6px 16px;
  }
  .title { flex: 1; max-width: none; }
  .desktop-action, .spacer { display: none; }
  .chat-header :deep(.agent-tag) { order: 4; flex-basis: 100%; min-width: 0; overflow-wrap: anywhere; }
  .context-box { flex-shrink: 0; }
  .context .meter { display: none; }
  .more { min-width: 44px; min-height: 44px; }
}
</style>
