<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PageLayout from '../components/PageLayout.vue'
import DropZone from '../components/pdfMerger/DropZone.vue'
import SourceList from '../components/pdfMerger/SourceList.vue'
import PageStrip from '../components/pdfMerger/PageStrip.vue'
import OutputPanel from '../components/pdfMerger/OutputPanel.vue'
import MergeBar from '../components/pdfMerger/MergeBar.vue'
import { useFilesStore } from '../stores/pdfMerger/files'
import { usePlanStore } from '../stores/pdfMerger/plan'
const files = useFilesStore()
const plan = usePlanStore()
onMounted(() => { void files.restore() })
function stop(): void { plan.stop(); files.stop() }
onBeforeUnmount(stop)
onBeforeRouteLeave(stop)
</script>
<template>
  <PageLayout title="PDF merger" description="Files are kept for 6 hours">
    <div class="workspace">
      <DropZone @files="files.upload($event)" />
      <p v-if="files.uploading" class="muted small" aria-live="polite">Uploading {{ files.uploading }} file(s)...</p>
      <ul v-if="files.errors.length" class="errors">
        <li v-for="(message,index) in files.errors" :key="index" role="alert">{{ message }} <button type="button" class="link" @click="files.dismissError(index)">Dismiss</button></li>
      </ul>
      <SourceList /><PageStrip /><OutputPanel /><MergeBar />
    </div>
  </PageLayout>
</template>
<style scoped>
:deep(.muted) { color: var(--muted); }
:deep(.small) { font-size: 12px; }
:deep(.error) { color: var(--danger); }

:deep(.workspace) { max-width: 920px; margin: 0 auto; padding: 0; display: grid; gap: 16px; }

:deep(.panel) { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 12px; }
:deep(.panel-head) { display: flex; align-items: baseline; gap: 12px; }
:deep(.panel-head h2) { flex: 1; }

:deep(button.primary), :deep(button.link), :deep(button.icon) { font: inherit; color: inherit; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-full); padding: 6px 10px; cursor: pointer; }
:deep(button:hover:not(:disabled)) { border-color: var(--muted); }
:deep(button:disabled) { opacity: 0.5; cursor: not-allowed; }
:deep(button.primary) { background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); padding: 8px 18px; }
:deep(button.primary .icon) { stroke: currentColor; }
:deep(button.link) { border: none; padding: 0 4px; color: var(--accent); }
:deep(button.icon) { min-width: 34px; }
:deep(input), :deep(select) { font: inherit; color: inherit; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 6px 8px; }
:deep(input.invalid) { border-color: var(--danger); }

:deep(.dropzone) { border: 1.5px dashed var(--muted); border-radius: var(--radius-lg); background: var(--surface); padding: 24px; text-align: center; cursor: pointer; }
:deep(.dropzone.over) { border-color: var(--accent); }
:deep(.dropzone-title) { margin: 0 0 4px; font-size: 15px; }
:deep(.dropzone p:last-of-type) { margin: 0; }

:deep(.source-list), :deep(.strip), :deep(.errors) { list-style: none; margin: 0; padding: 0; }
:deep(.source-list li + li) { border-top: 1px solid var(--border); }
:deep(.source-list li.dragging), :deep(.strip li.dragging) { opacity: 0.4; }
:deep(.source-list li:focus-visible), :deep(.strip li:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
:deep(.source-row) { display: flex; align-items: center; gap: 10px; padding: 8px 4px; }
:deep(.handle) { color: var(--muted); cursor: grab; }
:deep(.kind) { font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: var(--radius-sm); }
:deep(.kind.pdf) { color: var(--danger); border: 1px solid var(--danger); }
:deep(.kind.image) { color: var(--accent); border: 1px solid var(--accent); }
:deep(.meta) { flex: 1; min-width: 0; }
:deep(.name) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.control) { width: 130px; }
:deep(.control input), :deep(.control select) { width: 100%; box-sizing: border-box; }

:deep(.strip) { display: flex; flex-wrap: wrap; gap: 10px; }
:deep(.strip li) { cursor: grab; }
:deep(.thumb) { margin: 0; width: 96px; text-align: center; }
:deep(.paper) { width: 96px; height: 128px; display: flex; align-items: center; justify-content: center; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; transition: transform 0.15s; }
:deep(.paper canvas), :deep(.paper img) { max-width: 100%; max-height: 100%; }
:deep(.thumb figcaption) { margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

:deep(.grid) { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
:deep(.grid > label:not(.toggle)) { display: grid; gap: 4px; font-size: 12px; color: var(--muted); }

:deep(.merge-bar) { position: sticky; bottom: 0; display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); }
:deep(.merge-bar .status) { flex: 1; font-size: 13px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
:deep(.merge-bar a) { color: var(--accent); }

@media (max-width: 600px) {
:deep(.source-row) { flex-wrap: wrap; }
:deep(.control) { width: 100%; order: 5; }
}

:deep(.workspace) { width: 100%; min-width: 0; }
:deep(.workspace h2) { font-size: 1em; margin: 0 0 8px; }
:deep(.workspace :is(button,input,select,[tabindex]):focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
:deep(.workspace input,.workspace select) { min-width: 0; max-width: 100%; }
:deep(.workspace .grid) { grid-template-columns: repeat(auto-fit,minmax(min(200px,100%),1fr)); }
:deep(.workspace .source-row .danger) { color: var(--danger); border-color: var(--danger); }

:deep(button.primary[aria-busy="true"]) { display: inline-flex; align-items: center; gap: 8px; }
:deep(button.primary[aria-busy="true"]::before) { content: ''; width: 12px; height: 12px; border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full); animation: pdf-spin 0.7s linear infinite; }
@keyframes pdf-spin { to { transform: rotate(360deg); } }
</style>
