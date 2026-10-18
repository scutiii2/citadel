<script setup lang="ts">
import { ref } from "vue";
import { FORGE_FOLDER_MAX } from "../api/ForgeClient";
import { errorMessage } from "../utils/errors";

/** A folder path with a Browse… button. Browse asks the worker to open a folder dialog on its own
 * computer (a page cannot see that disk), so it only works for an online worker: `browse` is null
 * otherwise, and `unavailable` says why. Typing a path always works. */
const props = defineProps<{
  label: string;
  browse: ((start: string) => Promise<string | null>) | null;
  unavailable?: string;
  disabled?: boolean;
  placeholder?: string;
}>();
const model = defineModel<string>({ required: true });

const waiting = ref(false);
const error = ref("");

async function choose(): Promise<void> {
  if (!props.browse || waiting.value) return;
  waiting.value = true;
  error.value = "";
  try {
    const path = await props.browse(model.value.trim());
    if (path) model.value = path;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    waiting.value = false;
  }
}
</script>

<template>
  <div class="field">
    <label>
      <span>{{ label }}</span>
      <span class="row">
        <input
          v-model="model"
          type="text"
          :maxlength="FORGE_FOLDER_MAX"
          :disabled="disabled"
          autocomplete="off"
          spellcheck="false"
          :placeholder="placeholder"
        />
        <button
          type="button"
          class="browse"
          :disabled="disabled || !browse || waiting"
          :title="!browse ? unavailable : undefined"
          :aria-busy="waiting"
          @click="choose"
        >
          {{ waiting ? "Waiting…" : "Browse…" }}
        </button>
      </span>
    </label>
    <p v-if="waiting" class="note">A folder dialog is open on that worker's computer.</p>
    <p v-else-if="!browse && unavailable" class="note">{{ unavailable }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row {
  display: flex;
  gap: 8px;
}
input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
  font-family: var(--mono);
}
input:focus {
  border-color: var(--accent);
}
.browse {
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text);
  padding: 8px 14px;
  font: inherit;
  cursor: pointer;
  white-space: nowrap;
}
.browse:disabled {
  opacity: 0.5;
  cursor: default;
}
.note {
  margin: 0;
  color: var(--muted);
  font-size: 0.85em;
}
.error {
  margin: 0;
  color: var(--danger);
  font-size: 0.9em;
}
</style>
