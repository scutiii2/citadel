<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { FORGE_FOLDER_MAX, type ForgeGroup, type ForgeWorker } from "../api/ForgeClient";
import BaseModal from "./BaseModal.vue";

const props = defineProps<{ open: boolean; group: ForgeGroup | null; workers: ForgeWorker[]; busy: boolean; error: string }>();
const emit = defineEmits<{ close: []; invite: [workerId: number, folder: string] }>();

const chosen = ref<number | null>(null);
const folder = ref("");

const memberIds = computed(() => new Set(props.group?.members.map((m) => m.worker_id) ?? []));
const canInvite = computed(() => chosen.value !== null && folder.value.trim() !== "" && !props.busy);

function reason(worker: ForgeWorker): string {
  if (memberIds.value.has(worker.id)) return "Already in this group";
  return worker.eligible ? "" : (worker.problem ?? "Not eligible");
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    chosen.value = null;
    // Workers on one computer usually share a project folder, so start from the group's.
    folder.value = props.group?.members[0]?.folder ?? "";
  },
  { immediate: true },
);

function submit(): void {
  if (canInvite.value) emit("invite", chosen.value!, folder.value.trim());
}
</script>

<template>
  <BaseModal :open="open" title="Invite a worker" @close="emit('close')">
    <p v-if="!workers.length" class="muted">Add a worker first. Use Workers at the top of the page to pair one.</p>
    <form v-else @submit.prevent="submit">
      <fieldset :disabled="busy">
        <legend>Worker</legend>
        <label v-for="w in workers" :key="w.id" class="choice" :class="{ off: reason(w) !== '' }">
          <input v-model="chosen" type="radio" name="worker" :value="w.id" :disabled="reason(w) !== ''" />
          <span class="name">@{{ w.label }}</span>
          <span class="muted">{{ w.provider }}{{ w.reported_plan ? ` · ${w.reported_plan}` : "" }}</span>
          <span v-if="reason(w)" class="why">{{ reason(w) }}</span>
        </label>
      </fieldset>
      <label class="folder">
        <span>Folder on that worker's computer</span>
        <input v-model="folder" type="text" :maxlength="FORGE_FOLDER_MAX" autocomplete="off" spellcheck="false" placeholder="C:\Users\you\Projects\site" />
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="button" class="cancel" @click="emit('close')">Cancel</button>
        <button type="submit" class="confirm" :disabled="!canInvite" :aria-busy="busy">Invite</button>
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
fieldset {
  border: 0;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
legend {
  font-weight: 600;
  margin-bottom: 6px;
}
.choice {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  cursor: pointer;
}
.choice.off {
  opacity: 0.65;
  cursor: default;
}
.name {
  font-weight: 600;
  color: var(--accent);
}
.muted,
.why {
  color: var(--muted);
  font-size: 0.85em;
}
.why {
  margin-left: auto;
}
.folder {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.folder input {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
  font-family: var(--mono);
}
.folder input:focus {
  border-color: var(--accent);
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
