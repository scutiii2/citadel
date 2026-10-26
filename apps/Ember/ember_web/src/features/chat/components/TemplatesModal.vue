<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { TEMPLATE_BODY_MAX, TEMPLATE_NAME_MAX, type PromptTemplate } from "../api/TemplatesClient";
import { useTemplatesStore } from "../stores/templates";
import { errorMessage } from "../../../utils/errors";
import { preview } from "../utils/templates";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";

/** Create, edit and delete the account's saved prompts. Opened with
 * `draft` (the text typed in the chat input) it starts on a new template
 * holding that text: "save what I typed". */

const props = defineProps<{ open: boolean; draft: string }>();
const emit = defineEmits<{ close: [] }>();

const store = useTemplatesStore();

const nameInput = ref<HTMLInputElement | null>(null);

// null: the list; otherwise the form, for a new template (id null) or an existing one.
const editing = ref<{ id: string | null } | null>(null);
const name = ref("");
const body = ref("");
const error = ref("");
const saving = ref(false);
const initial = ref({ name: "", body: "" });
const dirty = computed(() => !!editing.value && (name.value !== initial.value.name || body.value !== initial.value.body));
const pendingDeparture = ref<"back" | "close" | null>(null);
function requestDeparture(destination: "back" | "close"): void {
  if (saving.value) return;
  if (dirty.value) { pendingDeparture.value = destination; return; }
  backToList();
  if (destination === "close") emit("close");
}
function discard(): void {
  const destination = pendingDeparture.value;
  pendingDeparture.value = null;
  backToList();
  if (destination === "close") emit("close");
}

const canSave = computed(() => name.value.trim() !== "" && body.value.trim() !== "" && !saving.value);

function startEdit(template: PromptTemplate | null, prefill = ""): void {
  if (saving.value) return;
  editing.value = { id: template?.id ?? null };
  name.value = template?.name ?? "";
  body.value = template?.body ?? prefill;
  initial.value = { name: name.value, body: template?.body ?? "" };
  error.value = "";
  void nextTick(() => nameInput.value?.focus());
}

function backToList(): void {
  editing.value = null;
  error.value = "";
}

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return;
    await nextTick();
    void store.ensureLoaded();
    if (!editing.value) {
      if (props.draft.trim()) startEdit(null, props.draft);
      else backToList();
    }
  },
);

async function save(): Promise<void> {
  if (!canSave.value || !editing.value) return;
  const editor = editing.value;
  saving.value = true;
  error.value = "";
  try {
    const { id } = editor;
    if (id === null) await store.create(name.value, body.value);
    else await store.update(id, name.value, body.value);
    if (editing.value === editor) backToList();
  } catch (err) {
    if (editing.value === editor) error.value = errorMessage(err);
  } finally {
    if (editing.value === editor || editing.value === null) saving.value = false;
  }
}

// Deleting a prompt asks first, in the confirmation dialog.
const pendingDelete = ref<PromptTemplate | null>(null);

async function remove(template: PromptTemplate): Promise<void> {
  pendingDelete.value = null;
  error.value = "";
  try {
    await store.remove(template.id);
  } catch (err) {
    error.value = errorMessage(err);
  }
}

const title = computed(() => (editing.value ? (editing.value.id === null ? "New prompt" : "Edit prompt") : "Saved prompts"));

// Esc, the × and a click outside step back from the form to the list, then close.
function onCancel(): void {
  requestDeparture(editing.value ? "back" : "close");
}
</script>

<template>
  <BaseModal :open="open" :title="title" @close="onCancel">
    <form v-if="editing" class="form" @submit.prevent="save">
      <label>
        Name
        <input ref="nameInput" v-model="name" :disabled="saving" type="text" :maxlength="TEMPLATE_NAME_MAX" autocomplete="off" />
      </label>
      <label>
        Text
        <textarea v-model="body" :disabled="saving" rows="8" :maxlength="TEMPLATE_BODY_MAX" />
      </label>
      <small class="count">{{ body.length.toLocaleString() }} / {{ TEMPLATE_BODY_MAX.toLocaleString() }}</small>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="buttons">
        <button type="button" class="pill-btn ghost" @click="requestDeparture('back')" :disabled="saving">Back</button>
        <button type="submit" class="pill-btn primary" :aria-busy="saving" :disabled="!canSave">{{ saving ? "Saving …" : "Save" }}</button>
      </div>
    </form>

    <template v-else>
      <p v-if="store.loadError" class="error" role="alert">
        {{ store.loadError }} <button type="button" class="link" @click="store.reload()">Retry</button>
      </p>
      <p v-else-if="store.loading && store.templates.length === 0" class="muted">Loading …</p>
      <p v-else-if="store.templates.length === 0" class="muted">
        No saved prompts yet. Type "#" in the chat input to use them.
      </p>
      <ul v-else class="list">
        <li v-for="t in store.templates" :key="t.id">
          <div class="info">
            <strong>{{ t.name }}</strong>
            <span class="muted">{{ preview(t.body, 70) }}</span>
          </div>
          <button type="button" class="link" @click="startEdit(t)">Edit</button>
          <button type="button" class="link danger" @click="pendingDelete = t">Delete</button>
        </li>
      </ul>
      <p v-if="error && !store.loadError" class="error" role="alert">{{ error }}</p>
      <div class="buttons">
        <button type="button" class="pill-btn primary" @click="startEdit(null)">New prompt</button>
      </div>
    </template>
    <ConfirmModal v-if="pendingDeparture" open title="Discard prompt changes?" message="Your prompt has unsaved changes." confirm-label="Discard" danger @confirm="discard" @close="pendingDeparture = null" />
    <ConfirmModal
      v-if="pendingDelete"
      open
      title="Delete prompt"
      :message="`Delete the prompt &quot;${pendingDelete.name}&quot;?`"
      confirm-label="Delete"
      danger
      @confirm="remove(pendingDelete)"
      @close="pendingDelete = null"
    />
  </BaseModal>
</template>

<style scoped>
.list {
  margin: 0 0 12px;
  padding: 0;
  list-style: none;
}
.list li {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.info span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 0.85em;
}
.muted {
  color: var(--muted);
}
.form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85em;
  color: var(--muted);
}
.form input,
.form textarea {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  outline: none;
  resize: vertical;
  color: var(--text);
  background: var(--bg);
  font: inherit;
}
.form input:focus,
.form textarea:focus {
  border-color: var(--accent);
}
.count {
  align-self: flex-end;
  color: var(--muted);
}
.error {
  margin: 0;
  font-size: 0.9em;
  color: var(--danger);
}
.buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.link {
  padding: 2px 8px;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.85em;
  color: var(--muted);
  background: transparent;
}
.link:hover {
  color: var(--text);
  background: var(--bg);
}
.link.danger:hover {
  color: var(--danger);
}

</style>
