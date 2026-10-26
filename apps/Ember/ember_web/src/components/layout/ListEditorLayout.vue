<script setup lang="ts">
import WorkspaceLayout from "./WorkspaceLayout.vue";

/** A list on the left and an editor form on the right (Notes, Memory). On a
 * narrow screen one at a time: the list, or the editor with a back button.
 * The editor owns the head (back button + `head` slot), a scrolling body (`editor`
 * slot) and the footer with the unsaved marker and Save. The feature keeps its
 * state, rows and confirmations. Use inside PageLayout `wide fill` with the
 * `info-content` class (the shared button and marker styles live in infoPage.css).
 * Page-head tweaks for a narrow screen stay with the page. */
withDefaults(defineProps<{
  /** True while an editor is open; false shows the `placeholder` slot. */
  editing: boolean;
  listLabel?: string;
  editorLabel?: string;
  /** Text after the back arrow, e.g. "All notes". */
  backLabel: string;
  /** Disables Back and shows the busy state of Save while true. */
  busy?: boolean;
  saving?: boolean;
  dirty?: boolean;
  canSave?: boolean;
  /** Show "No unsaved changes" when the draft is clean. */
  showSavedState?: boolean;
}>(), { listLabel: undefined, editorLabel: undefined, busy: false, saving: false, dirty: false, canSave: false, showSavedState: false });

defineEmits<{ back: []; submit: [] }>();
</script>

<template>
  <WorkspaceLayout class="list-editor" :class="{ editing }">
    <aside class="list-pane" :aria-label="listLabel">
      <slot name="list" />
    </aside>
    <form v-if="editing" class="editor" :aria-label="editorLabel" @submit.prevent="$emit('submit')">
      <header class="editor-head">
        <button type="button" class="chip back" :disabled="busy" @click="$emit('back')">‹ {{ backLabel }}</button>
        <slot name="head" />
      </header>
      <div class="editor-scroll"><slot name="editor" /></div>
      <footer class="actions">
        <span v-if="dirty" class="unsaved" role="status"><i aria-hidden="true" />Unsaved changes</span>
        <span v-else-if="showSavedState" class="saved-state">No unsaved changes</span>
        <button type="submit" class="primary" :disabled="!canSave" :aria-busy="saving">{{ saving ? "Saving…" : "Save" }}</button>
      </footer>
    </form>
    <div v-else class="placeholder"><slot name="placeholder" /></div>
  </WorkspaceLayout>
</template>

<style scoped>
.list-pane { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; background: color-mix(in srgb, var(--surface) 50%, var(--bg)); border-right: 1px solid var(--border); padding: 20px 12px; }
.editor { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--bg); }
.editor-head { display: flex; align-items: center; gap: 16px; padding: 16px 28px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.editor-scroll { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; overflow-wrap: anywhere; scroll-padding: 20px; }
.actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 14px 28px; border-top: 1px solid var(--border); flex-shrink: 0; background: var(--bg); }
.actions .primary { min-width: 76px; min-height: 40px; }
.actions .primary[aria-busy="true"]::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 7px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); vertical-align: -1px; animation: save-spin .7s linear infinite; }
@keyframes save-spin { to { transform: rotate(360deg); } }
.back { display: none; }
.list-editor :is(button, summary, input, textarea):focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (max-width: 900px) and (min-width: 768px) { .list-editor { --workspace-columns: 220px minmax(0, 1fr); } .actions { padding-inline: 20px; } }
@media (max-width: 767px) {
  .list-editor.editing .list-pane, .list-editor:not(.editing) .placeholder { display: none; }
  .list-pane { border-right: 0; padding: 16px 10px; }
  .editor-head { padding: 12px 16px; justify-content: space-between; gap: 10px; }
  .back { display: inline-block; min-height: 44px; }
  .actions { padding: 12px 16px; }
  .actions .primary { min-height: 44px; }
}
</style>
