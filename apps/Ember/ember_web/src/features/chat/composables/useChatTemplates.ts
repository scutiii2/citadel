import { computed, ref, watch } from "vue";
import type { ChatMessage } from "../../../api/types";
import { useTemplatesStore } from "../stores/templates";

/** Saved-prompt loading and dialogs for the active conversation. */
export function useChatTemplates(messages: () => ChatMessage[]) {
  const templates = useTemplatesStore();

  // The saved-prompts dialog; `templatesDraft` is typed text offered as a new prompt.
  const templatesOpen = ref(false);
  const templatesDraft = ref("");

  function openTemplates(draft: string): void {
    templatesDraft.value = draft;
    templatesOpen.value = true;
  }

  // The question Save buttons compare against. Loaded once the chat holds a
  // question of yours, so a chat without one never asks for the list.
  const savedPrompts = computed(() => templates.templates.map((t) => t.body.trim()));
  watch(
    () => messages().some((m) => m.role === "user"),
    (hasQuestion) => {
      if (hasQuestion) void templates.ensureLoaded();
    },
    { immediate: true },
  );

  /** Save on a question: a new prompt holding it, or the saved-prompts list when it already is one. */
  function saveAsPrompt(text: string): void {
    openTemplates(savedPrompts.value.includes(text.trim()) ? "" : text);
  }


  return { templates, templatesOpen, templatesDraft, savedPrompts, openTemplates, saveAsPrompt };
}
