<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { CommandInfo } from "../api/CommandsClient";
import type { JsonSchema } from "../api/types";
import { commandText } from "../utils/toolSchema";
import ToolRunForm from "./ToolRunForm.vue";

/** Fills a slash command's parameters from a form (port of chat_app's
 * command-form modal) instead of typing key=value by hand. Submitting
 * builds the same "/<capability> <command> key=value ..." text a user could
 * type, which the chat then runs. */

const props = defineProps<{ command: CommandInfo | null; schema: JsonSchema | null; chatId?: string | null }>();
const emit = defineEmits<{ submit: [text: string]; close: [] }>();

// Manual ticket provenance comes from the chat, rather than user input.
const manualTicket = computed(() => props.command?.tool_name === "tool_ticket_createTicket");
const formSchema = computed(() => {
  if (!manualTicket.value || !props.schema) return props.schema;
  const automatic = new Set(["source", "chat_id"]);
  return {
    ...props.schema,
    properties: Object.fromEntries(Object.entries(props.schema.properties ?? {}).filter(([name]) => !automatic.has(name))),
    required: props.schema.required?.filter((name) => !automatic.has(name)),
  };
});

const dialog = ref<HTMLDialogElement | null>(null);

watch(
  () => props.command && props.schema,
  async (open) => {
    await nextTick();
    if (open && !dialog.value?.open) dialog.value?.showModal();
    else if (!open && dialog.value?.open) dialog.value.close();
  },
);

function run(args: Record<string, unknown>): void {
  if (!props.command) return;
  const context: Record<string, unknown> = {};
  if (manualTicket.value) {
    if (props.schema?.properties?.source) context.source = "user";
    if (props.schema?.properties?.chat_id && props.chatId) context.chat_id = props.chatId;
  }
  emit("submit", commandText(props.command.capability, props.command.name, { ...args, ...context }));
}
</script>

<template>
  <dialog ref="dialog" class="command-form" @close="emit('close')" @cancel.prevent="emit('close')">
    <template v-if="command && schema">
      <header>
        <h3><code>/{{ command.capability }} {{ command.name }}</code></h3>
        <button type="button" class="close" aria-label="Close" @click="emit('close')">×</button>
      </header>
      <p v-if="command.description" class="description">{{ command.description }}</p>
      <p v-if="manualTicket && chatId" class="description">This ticket is linked to the current chat automatically.</p>
      <ToolRunForm v-if="formSchema" :key="command.tool_name" :schema="formSchema" :running="false" submit-label="Run command" @run="run" />
    </template>
  </dialog>
</template>

<style scoped>
.command-form {
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100vh - 64px);
  padding: 18px 20px 20px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  color: var(--text);
  background: var(--surface);
}
.command-form::backdrop {
  background: rgb(0 0 0 / 45%);
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
h3 {
  margin: 0;
  font-size: 1em;
}
h3 code {
  font-family: var(--mono);
}
.close {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 1.4em;
  line-height: 1;
  color: var(--muted);
}
.description {
  margin: 6px 0 14px;
  font-size: 0.9em;
  color: var(--muted);
}
</style>
