<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from "vue";
import DangerZone from "../../../components/ui/status/DangerZone.vue";
import CharacterCount from "../../../components/ui/status/CharacterCount.vue";
import TagInput from "../../../components/ui/forms/TagInput.vue";
import { ToggleSwitch } from "@citadel/ui";
import { growOnResize, growToContent } from "../../../utils/browser/autoGrow";
import { FILE_TAG_MAX, FILE_TAGS_MAX, FILE_TITLE_MAX, normalizeFolder, normalizeTag, type BrainFile } from "../api/BrainClient";

/** The right pane of the Notes page: the fields of one file and what the user may do with it. It holds no
 * state of its own; the page owns the draft, saves it and answers `revert` and `remove`. */
const props = defineProps<{
  /** The saved file's details; null for a file not saved yet. */
  file: Pick<BrainFile, "source" | "last_editor" | "edited" | "warning" | "shared_from"> | null;
  folders: string[];
  /** Tags the account already uses, most used first. */
  knownTags: { tag: string; count: number }[];
  /** The live limit for one file's text. */
  maxChars: number;
  /** Why the folder cannot be saved, or "". */
  folderProblem: string;
  canRevert: boolean;
  /** Why Restore original is off, or "". */
  revertHint: string;
  canShare: boolean;
  shareHint: string;
  disabled: boolean;
}>();

const title = defineModel<string>("title", { required: true });
const body = defineModel<string>("body", { required: true });
const tags = defineModel<string[]>("tags", { required: true });
const tagText = defineModel<string>("tagText", { required: true });
const folder = defineModel<string>("folder", { required: true });
const agentEditable = defineModel<boolean>("agentEditable", { required: true });
defineEmits<{ revert: []; remove: []; share: [] }>();

const uid = useId();
const titleField = ref<HTMLInputElement | null>(null);
const bodyField = ref<HTMLTextAreaElement | null>(null);
const tagField = ref<InstanceType<typeof TagInput> | null>(null);

// Grow the text within the editor scroller, including after a viewport resize.
watch([body, bodyField], async () => {
  await nextTick();
  if (bodyField.value) growToContent(bodyField.value);
});
growOnResize(bodyField);

const folderHint = computed(() => folder.value.trim() || "No folder");
const agentHint = computed(() => (props.file?.source === "automatic" || agentEditable.value ? "Agents can edit" : "Agents can read"));

defineExpose({
  /** A tag still in the box is part of the file: add it before saving. */
  commitTags: () => tagField.value?.commit(),
  focusTitle: () => titleField.value?.focus(),
});
</script>

<template>
  <div class="file-editor">
    <div class="writing">
      <p v-if="file?.source === 'automatic'" class="notice warn" role="note" data-test="agent-warning">
        <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
        {{ file.warning || "Written by an agent. Editing it may break the agent that uses it." }}
      </p>
      <p v-else-if="file?.source === 'shared'" class="notice" role="note" data-test="shared-note">
        {{ file.shared_from ? `Shared by ${file.shared_from}.` : "Shared with you." }} This is your own copy; you can edit it.
      </p>
      <p v-else-if="file?.last_editor === 'agent'" class="notice" role="note">
        An agent last changed this file. Saving your own changes removes this mark.
      </p>
      <label class="title-field">
        <span class="sr-only">Title</span>
        <input ref="titleField" v-model="title" type="text" :maxlength="FILE_TITLE_MAX" aria-label="Title" :aria-describedby="`${uid}-title-count`" placeholder="Untitled file" :disabled="disabled" />
        <CharacterCount :id="`${uid}-title-count`" class="count" :length="title.length" :max="FILE_TITLE_MAX" />
      </label>
      <label class="body-field">
        <span class="sr-only">File text</span>
        <textarea ref="bodyField" v-model="body" rows="10" placeholder="Start writing…" :maxlength="maxChars" aria-label="File text" :aria-describedby="`${uid}-body-count`" :disabled="disabled" />
        <CharacterCount :id="`${uid}-body-count`" class="count" :length="body.length" :max="maxChars" />
      </label>
    </div>
    <div class="tools">
      <details class="folder-tools">
        <summary><span>Folder and tags</span><span class="summary-hint">{{ folderHint }}{{ tags.length ? ` · ${tags.join(", ")}` : "" }} <span aria-hidden="true">›</span></span></summary>
        <div class="field">
          <span class="field-label">Folder</span>
          <input v-model="folder" type="text" maxlength="130" aria-label="Folder" placeholder="No folder (top level)" :disabled="disabled" @blur="folder = normalizeFolder(folder)" />
          <p v-if="folderProblem" class="error" role="alert">{{ folderProblem }}</p>
          <div v-if="folders.length" class="picks">
            <span class="muted">Existing folders:</span>
            <button v-for="name in folders" :key="name" type="button" class="chip" :aria-label="`Use folder ${name}`" :disabled="disabled" @click="folder = name">{{ name }}</button>
          </div>
          <span class="field-label">Tags</span>
          <TagInput ref="tagField" v-model="tags" v-model:text="tagText" :known="knownTags" :normalize="normalizeTag" :max="FILE_TAGS_MAX" :max-length="FILE_TAG_MAX" :disabled="disabled" />
        </div>
      </details>
      <details class="agent-tools">
        <summary><span>Agent access</span><span class="summary-hint">{{ agentHint }} <span aria-hidden="true">›</span></span></summary>
        <div class="field">
          <p class="muted hint">Agents can read every file here. Do not store passwords, keys or other private data.</p>
          <p v-if="file?.source === 'automatic'" class="muted hint">An agent wrote this file, so agents can edit it.</p>
          <ToggleSwitch v-else-if="file" :checked="agentEditable" :disabled="disabled" @change="agentEditable = ($event.target as HTMLInputElement).checked">
            Let agents edit this file
          </ToggleSwitch>
        </div>
      </details>
      <details v-if="file?.edited" class="original-tools">
        <summary><span>Original text</span><span aria-hidden="true">›</span></summary>
        <div class="field">
          <p class="muted hint">You changed this file. The text from before your first change is kept.</p>
          <div><button type="button" class="chip" :disabled="!canRevert || disabled" @click="$emit('revert')">Restore original</button></div>
          <p v-if="revertHint" class="muted hint">{{ revertHint }}</p>
        </div>
      </details>
      <details v-if="file" class="share-tools">
        <summary><span>Share</span><span aria-hidden="true">›</span></summary>
        <div class="field">
          <p class="muted hint">Send a copy of the saved file, or one section of it, to another account or to the global brain. They decide whether to keep it.</p>
          <div><button type="button" class="chip" :disabled="!canShare || disabled" @click="$emit('share')">Share a copy…</button></div>
          <p v-if="shareHint" class="muted hint">{{ shareHint }}</p>
        </div>
      </details>
      <details v-if="file" class="manage-tools">
        <summary>Manage file <span aria-hidden="true">›</span></summary>
        <DangerZone class="danger-zone"><template #label><b>Danger zone</b></template><button type="button" class="danger" :disabled="disabled" @click="$emit('remove')">Delete this file</button></DangerZone>
      </details>
    </div>
  </div>
</template>

<style scoped src="../../../components/layout/editorPage.css"></style>
<style scoped>
.file-editor { display: flex; flex: 1; flex-direction: column; min-height: 0; }
.title-field, .body-field { display: flex; flex-direction: column; min-width: 0; gap: 10px; }
.title-field input { width: 100%; padding: 0; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text); font: inherit; font-size: 1.65em; font-weight: 600; letter-spacing: -.025em; line-height: 1.4; }
.body-field { flex: 1; gap: 12px; }
.body-field textarea { width: 100%; min-height: 230px; padding: 0; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text); font: inherit; line-height: 1.9; resize: none; overflow-y: hidden; }
.count { align-self: flex-end; }
.notice { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); font-size: .85em; }
.notice.warn { border-color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, var(--bg)); }
.notice.warn .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.tools { flex-shrink: 0; border-top: 1px solid var(--border); padding: 0 28px; }
.tools > details + details { border-top: 1px solid var(--border); }
summary > [aria-hidden], .summary-hint { color: var(--muted); }
.summary-hint { font-size: .9em; min-width: 0; text-align: right; overflow-wrap: anywhere; }
.tools details[open] > summary { color: var(--accent); }
.field { display: flex; flex-direction: column; gap: 12px; padding: 0 0 16px; }
.field-label { font-size: .85em; color: var(--muted); }
.field input[type="text"] { width: 100%; }
.picks { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.hint { margin: 0; font-size: .85em; }
.danger-zone { margin-bottom: 16px; }
@media (max-width: 900px) and (min-width: 768px) { .tools { padding-inline: 20px; } }
@media (max-width: 767px) {
  .title-field input { font-size: 1.45em; }
  .body-field textarea { min-height: 250px; }
  .tools { padding-inline: 20px; }
  summary, .tools button { min-width: 44px; min-height: 44px; }
}
</style>
