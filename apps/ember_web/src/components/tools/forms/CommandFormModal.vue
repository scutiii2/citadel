<script setup lang="ts">
import { computed } from "vue";
import type { CommandInfo } from "../../../api/tools/CommandsClient";
import type { JsonSchema } from "../../../api/types";
import { commandText } from "../../../utils/tools/toolSchema";
import BaseModal from "../../ui/dialogs/BaseModal.vue";
import ToolRunForm from "./ToolRunForm.vue";

/** Fills a slash command's parameters from a form (port of chat_app's
 * command-form modal) instead of typing key=value by hand. Submitting
 * builds the same "/<capability> <command> key=value ..." text a user could
 * type, which the chat then runs. */

const props = defineProps<{ command: CommandInfo | null; schema: JsonSchema | null }>();
const emit = defineEmits<{ submit: [text: string]; close: [] }>();

const title = computed(() => (props.command ? `/${props.command.capability} ${props.command.name}` : ""));

function run(args: Record<string, unknown>): void {
  if (!props.command) return;
  emit("submit", commandText(props.command.capability, props.command.name, args));
}
</script>

<template>
  <BaseModal :open="!!(command && schema)" :title="title" @close="emit('close')">
    <template v-if="command && schema">
      <p v-if="command.description" class="description">{{ command.description }}</p>
      <ToolRunForm :key="command.tool_name" :schema="schema" :running="false" submit-label="Run command" @run="run" />
    </template>
  </BaseModal>
</template>

<style scoped>
.description {
  margin: 6px 0 14px;
  font-size: 0.9em;
  color: var(--muted);
}
</style>
