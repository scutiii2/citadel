<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PageLayout from '../components/PageLayout.vue'
import ActionButton from '../components/ActionButton.vue'
import BaseModal from '../components/BaseModal.vue'
import SegmentedControl from '../components/SegmentedControl.vue'
import DropZone from '../components/pdfMerger/DropZone.vue'
import SourceList from '../components/pdfMerger/SourceList.vue'
import PageStrip from '../components/pdfMerger/PageStrip.vue'
import OutputPanel from '../components/pdfMerger/OutputPanel.vue'
import MergeBar from '../components/pdfMerger/MergeBar.vue'
import { useFilesStore } from '../stores/pdfMerger/files'
import { usePlanStore } from '../stores/pdfMerger/plan'
import { useAuthStore } from '../stores/auth'
const files = useFilesStore()
const plan = usePlanStore()
const auth = useAuthStore()
const mode = ref<'pages' | 'files'>('pages')
const outputOpen = ref(false)
const dropZone = ref<InstanceType<typeof DropZone> | null>(null)
const modes = computed(() => [
  { value: 'pages' as const, label: `Pages · ${plan.pages.length}` },
  { value: 'files' as const, label: `Files · ${files.sources.length}` },
])
watch(() => auth.account?.id, () => { mode.value = 'pages'; outputOpen.value = false }, { flush: 'sync' })
onMounted(() => { void files.restore() })
function stop(): void { plan.stop(); files.stop() }
onBeforeUnmount(stop)
onBeforeRouteLeave(stop)
</script>
<template>
  <PageLayout class="pdf-page" title="PDF merger" description="Combine PDFs and images. Put every page in place." wide fill>
    <template #actions><button type="button" class="add-files" @click="dropZone?.openPicker()"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>Add files</button></template>
    <div v-if="files.uploading || files.errors.length" class="notices">
      <p v-if="files.uploading" class="muted small" role="status">Uploading {{ files.uploading }} file(s)...</p>
      <ul v-if="files.errors.length" class="errors"><li v-for="(message,index) in files.errors" :key="index" role="alert">{{ message }} <button type="button" class="link" @click="files.dismissError(index)">Dismiss</button></li></ul>
    </div>
    <div :class="['workspace', `mode-${mode}`]">
      <div class="mobile-tabs"><SegmentedControl v-model="mode" :options="modes" aria-label="PDF workspace" /></div>
      <div class="pages-panel">
        <PageStrip />
        <div v-if="!plan.pages.length" class="empty-pages">
          <h3>Your PDF starts here</h3><p class="muted">Add PDFs or images, choose the pages you need, then arrange them in order.</p>
          <button type="button" class="add-files" @click="dropZone?.openPicker()">Choose files</button>
        </div>
      </div>
      <aside class="files-panel" aria-label="Source files">
        <SourceList />
        <p v-if="!files.sources.length" class="muted small">Your source files will appear here.</p>
        <DropZone ref="dropZone" @files="files.upload($event)" />
        <p class="retention muted">Files are kept for 6 hours.<br>Save your merged PDF before it expires.</p>
      </aside>
      <footer class="output-area">
        <label class="output-label" for="pdf-output-name">Output file</label>
        <div class="output-row"><input id="pdf-output-name" v-model="plan.output.filename" aria-label="Output file" placeholder="merged.pdf" /><ActionButton icon="summarize" class="options-button" @click="outputOpen = true">Output options</ActionButton></div>
        <MergeBar />
      </footer>
    </div>
    <BaseModal :open="outputOpen" title="Output options" class="pdf-options-modal" @close="outputOpen = false"><OutputPanel /><p class="muted small">Options apply to your next merge.</p></BaseModal>
  </PageLayout>
</template>
<style scoped src="../components/pdfMerger/workspace.css"></style>
