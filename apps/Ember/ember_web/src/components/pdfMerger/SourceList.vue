<script setup lang="ts">
// Source files in default order; drag a row to reorder.
import { ref } from 'vue'
import { useFilesStore } from '../../stores/pdfMerger/files'
import ConfirmModal from '../ConfirmModal.vue'
import type { SourceState } from '../../stores/pdfMerger/files'
import SourceRow from './SourceRow.vue'

const files = useFilesStore()
const removing = ref<SourceState | null>(null)
const busy = ref(false)
async function confirmRemove(): Promise<void> {
  if (!removing.value || busy.value) return
  busy.value = true
  try { await files.remove(removing.value.info.file_id); removing.value = null } finally { busy.value = false }
}
const dragFrom = ref<number | null>(null)

function onDragStart(index: number, event: DragEvent): void {
  dragFrom.value = index
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', String(index))
    event.dataTransfer.effectAllowed = 'move'
  }
}

function onDragOver(event: DragEvent): void {
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function onKey(index: number, event: KeyboardEvent): void {
  if (event.target !== event.currentTarget) return // typed inside a child, e.g. the range input
  if (!event.altKey || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return
  event.preventDefault()
  const to = event.key === 'ArrowUp' ? index - 1 : index + 1
  if (to >= 0 && to < files.sources.length) files.moveSource(index, to)
}

function onDrop(index: number): void {
  if (dragFrom.value !== null) files.moveSource(dragFrom.value, index)
  dragFrom.value = null
}
</script>

<template>
  <section v-if="files.sources.length" class="panel">
    <h2>Source files</h2>
    <ol class="source-list" aria-label="Source files. Press Alt and an arrow key to move a file.">
      <li
        v-for="(source, index) in files.sources"
        :key="source.info.file_id"
        tabindex="0"
        :class="{ dragging: dragFrom === index }"
        @keydown="onKey(index, $event)"
        @dragover.prevent="onDragOver"
        @drop.prevent="onDrop(index)"
      >
        <SourceRow
          :source="source"
          @range="files.setRange(source.info.file_id, $event)"
          @rotate="files.rotate(source.info.file_id)"
          @fit="files.setFit(source.info.file_id, $event)"
          @remove="removing = source"
          @dragstart="onDragStart(index, $event)"
          @dragend="dragFrom = null"
        />
      </li>
    </ol>
    <ConfirmModal :open="removing !== null" title="Remove source file?" :message="`Remove ${removing?.info.name ?? 'this file'} from your files and merge plan?`" confirm-label="Remove" danger :busy="busy" @close="!busy && (removing = null)" @confirm="confirmRemove" />
  </section>
</template>
