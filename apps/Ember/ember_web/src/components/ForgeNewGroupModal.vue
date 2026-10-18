<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { FORGE_TITLE_MAX, type ForgeMode } from "../api/ForgeClient";
import { CREATE_MODE_OPTIONS, MODE_HELP } from "../utils/forgeModes";
import BaseModal from "./BaseModal.vue";
import SegmentedControl from "./SegmentedControl.vue";

type StartMode = Exclude<ForgeMode, "full_auto">;

const props = defineProps<{ open: boolean; busy: boolean; error: string }>();
const emit = defineEmits<{ close: []; create: [title: string, mode: StartMode] }>();

const title = ref("");
const mode = ref<StartMode>("ask");
const canCreate = computed(() => title.value.trim() !== "" && !props.busy);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    title.value = "";
    mode.value = "ask";
  },
);

function submit(): void {
  if (canCreate.value) emit("create", title.value.trim(), mode.value);
}
</script>

<template>
  <BaseModal :open="open" title="New group" @close="emit('close')">
    <form @submit.prevent="submit">
      <label class="field">
        <span>Title</span>
        <input v-model="title" type="text" :maxlength="FORGE_TITLE_MAX" autocomplete="off" placeholder="Build the new homepage" />
      </label>
      <div class="field">
        <span>Start in</span>
        <SegmentedControl v-model="mode" :options="CREATE_MODE_OPTIONS" aria-label="Starting mode" />
        <p class="muted">{{ MODE_HELP[mode] }}</p>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="button" class="cancel" @click="emit('close')">Cancel</button>
        <button type="submit" class="confirm" :disabled="!canCreate" :aria-busy="busy">Create</button>
      </div>
    </form>
  </BaseModal>
</template>

<style scoped>
form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field > span {
  font-weight: 600;
}
input[type="text"] {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
}
input[type="text"]:focus {
  border-color: var(--accent);
}
.muted {
  margin: 0;
  color: var(--muted);
  font-size: 0.85em;
}
.error {
  margin: 0;
  color: var(--danger);
  font-size: 0.9em;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.actions button {
  border-radius: var(--radius-full);
  padding: 8px 18px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.cancel {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
}
.confirm {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-contrast);
}
.confirm:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
