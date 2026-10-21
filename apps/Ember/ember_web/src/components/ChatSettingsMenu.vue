<script setup lang="ts">
// The chat page's settings behind a gear in the bar above the message box:
// closed on every load, closed again by Escape or a click anywhere else. The
// panel opens upward, since the bar is at the bottom of the page.
import { nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef } from "vue";
import { RouterLink } from "vue-router";
import { withTokenCost } from "../utils/tokenCosts";
import ToggleSwitch from "./ToggleSwitch.vue";

defineProps<{
  caveman: boolean;
  plan: boolean;
  /** Ask the agent to update its checklist only when an item changes status. */
  planLean: boolean;
  /** The agent asks before at least some tools (the picker next to this menu says how). */
  askBeforeTools: boolean;
  /** An administrator requires approval before every tool: not changeable. */
  forceToolApproval: boolean;
  chime: boolean;
  /** Tools already allowed for this chat. */
  allowedCount: number;
  enabledExtensions: string[];
  /** Puts a dot on the gear, e.g. while a tool waits for an answer. */
  attention: boolean;
  secondBrainAvailable?: boolean;
  secondBrainScope?: "instance" | "personal" | null;
  saveToSecondBrain?: boolean;
  secondBrainPending?: boolean;
}>();

const emit = defineEmits<{
  "update:caveman": [value: boolean];
  "update:plan": [value: boolean];
  "update:planLean": [value: boolean];
  "update:chime": [value: boolean];
  "update:saveToSecondBrain": [value: boolean];
  "update:secondBrainScope": [value: "instance" | "personal"];
  "clear-allowed": [];
}>();

const open = ref(false);
const root = useTemplateRef<HTMLElement>("root");
const gearButton = useTemplateRef<HTMLButtonElement>("gearButton");

function checked(event: Event): boolean {
  return (event.target as HTMLInputElement).checked;
}

function onDocumentClick(event: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false;
}

async function closeWithEscape(): Promise<void> {
  open.value = false;
  await nextTick();
  gearButton.value?.focus();
}

onMounted(() => document.addEventListener("click", onDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocumentClick));
</script>

<template>
  <div ref="root" class="settings-menu">
    <button
      ref="gearButton"
      type="button"
      class="gear"
      title="Chat settings"
      aria-label="Chat settings"
      aria-haspopup="true"
      :aria-expanded="open"
      @click="open = !open"
    >
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <circle cx="12" cy="12" r="3" />
        <path
          d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
        />
      </svg>
      <span v-if="attention" class="dot" aria-hidden="true" />
    </button>

    <div v-if="open" class="panel" role="group" aria-label="Chat settings" @keydown.esc.stop="closeWithEscape">
      <p class="note">Applies instantly. Saved on this device.</p>
      <template v-if="secondBrainAvailable">
          <label>Auto-save destination
            <select :value="secondBrainScope ?? ''" :disabled="secondBrainPending" @change="emit('update:secondBrainScope', ($event.target as HTMLSelectElement).value as 'instance' | 'personal')">
              <option disabled value="">Choose a brain</option><option value="personal">Personal Brain (only you)</option><option value="instance">Instance Brain (all signed-in users)</option>
            </select>
          </label>
        <ToggleSwitch
          small
          title="Ask the agent to save a summary after each exchange. Tool approval and vault write settings still apply."
          :checked="saveToSecondBrain ?? false"
          :disabled="secondBrainPending || secondBrainScope === null"
          :aria-busy="secondBrainPending ?? false"
          @change="emit('update:saveToSecondBrain', checked($event))"
        >Save to second brain</ToggleSwitch>
        <p class="note">Saved per chat on the server, with its first question. May require tool approval.</p>
      </template>
      <ToggleSwitch
        small
        :title="withTokenCost('Ask the agent for short, terse answers', 'terse')"
        :checked="caveman"
        @change="emit('update:caveman', checked($event))"
      >
        Terse replies
      </ToggleSwitch>
      <ToggleSwitch
        small
        :title="withTokenCost('Let the agent show a checklist while it works through a multi-step task', 'plan')"
        :checked="plan"
        @change="emit('update:plan', checked($event))"
      >
        Task checklist
      </ToggleSwitch>
      <ToggleSwitch
        v-if="plan"
        small
        class="sub"
        :title="withTokenCost('Ask the agent to change the checklist only when an item starts or finishes', 'planLean')"
        :checked="planLean"
        @change="emit('update:planLean', checked($event))"
      >
        Update only on change
      </ToggleSwitch>
      <button
        v-if="askBeforeTools && allowedCount && !forceToolApproval"
        type="button"
        class="allowed"
        title="Ask again about the tools you allowed for this chat"
        @click="emit('clear-allowed')"
      >
        {{ allowedCount }} tool{{ allowedCount === 1 ? "" : "s" }} allowed - reset
      </button>
      <ToggleSwitch
        small
        :title="withTokenCost('Play a short chime when an answer arrives while this tab is in the background', 'chime')"
        :checked="chime"
        @change="emit('update:chime', checked($event))"
      >
        Chime when done
      </ToggleSwitch>
      <RouterLink to="/settings" class="all-settings">All settings</RouterLink>
      <RouterLink to="/capabilities" class="extensions" title="Which extensions' tools the agent may use in your chats">
        Extensions: {{ enabledExtensions.length ? enabledExtensions.join(", ") : "off" }}
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.settings-menu {
  position: relative;
  z-index: 15;
}
.gear {
  position: relative;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--muted);
  background: var(--bg);
}
.gear:hover,
.gear[aria-expanded="true"] {
  color: var(--text);
  border-color: var(--accent);
}
.gear svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--accent);
}
.note {
  margin: 0;
  font-size: 0.8em;
  color: var(--muted);
}
.panel {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  width: max-content;
  max-width: min(320px, calc(100vw - 32px));
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
}
.sub {
  margin-left: 40px;
}
.allowed {
  margin-left: 40px;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  cursor: pointer;
  font-size: 0.75em;
  color: var(--muted);
  background: transparent;
}
.allowed:hover {
  color: var(--text);
  border-color: var(--accent);
}
.extensions,
.all-settings {
  font-size: 0.85em;
  color: var(--muted);
  text-decoration: none;
}
.extensions:hover,
.all-settings:hover {
  color: var(--text);
}
</style>
