<script setup lang="ts">
// Merge summary, progress, result and the merge button.
import { computed, ref } from 'vue'
import ConfirmModal from '../ConfirmModal.vue'
import CopyButton from '../CopyButton.vue'
import DownloadCards from '../DownloadCards.vue'
import ElapsedTime from '../ElapsedTime.vue'
import ActionButton from '../ActionButton.vue'
import { downloadUrl } from '../../api/PdfMergerClient'
import { formatBytes, plural } from '../../lib/pdfMerger/format'
import { usePlanStore } from '../../stores/pdfMerger/plan'

const plan = usePlanStore()
const cancelOpen = ref(false)
const cancelling = ref(false)
async function confirmCancel(): Promise<void> {
  if (cancelling.value) return
  cancelling.value = true
  try { await plan.cancel(); cancelOpen.value = false } finally { cancelling.value = false }
}


const summary = computed(() => {
  const fileCount = new Set(plan.pages.map((p) => p.fileId)).size
  return `${plural(plan.pages.length, 'page')} from ${plural(fileCount, 'file')}`
})
const percent = computed(() =>
  plan.progress.total ? Math.round((plan.progress.done / plan.progress.total) * 100) : 0,
)
</script>

<template>
  <div class="merge-bar">
    <div class="status" aria-live="polite">
      <template v-if="plan.status === 'running'">
        Merging… {{ plan.progress.done }} of {{ plan.progress.total }} pages
        <ElapsedTime :since="plan.startedAt" />
        <ActionButton icon="close" @click="cancelOpen = true">Cancel merge</ActionButton>
        <progress :value="percent" max="100" />
      </template>
      <template v-else-if="plan.status === 'done' && plan.result">
        Done · {{ plan.result.name }} ({{ formatBytes(plan.result.size) }})
        <DownloadCards :downloads="[{filename:plan.result.name, bytes:plan.result.size, href:downloadUrl(plan.result.file_id), label:'MERGED PDF'}]" />
        <CopyButton :text="plan.result.file_id" label="Copy merged file ID" />
      </template>
      <span v-else-if="plan.status === 'error'" class="error" role="alert">{{ plan.error }}</span>
      <span v-else-if="plan.hasRangeErrors" class="error">Fix the page ranges marked in red, then merge.</span>
      <template v-else-if="plan.pages.length">Ready to merge {{ summary }}</template>
      <template v-else>Add files to start</template>
    </div>
    <ActionButton icon="verify" class="primary" :disabled="!plan.canMerge" :aria-busy="plan.status === 'running'" @click="plan.merge()">
      {{ plan.status === 'running' ? 'Merging…' : 'Merge PDF' }}
    </ActionButton>
    <ConfirmModal :open="cancelOpen" title="Cancel merge?" message="Stop the current PDF merge?" confirm-label="Cancel merge" :busy="cancelling" @close="!cancelling && (cancelOpen = false)" @confirm="confirmCancel" />
  </div>
</template>
