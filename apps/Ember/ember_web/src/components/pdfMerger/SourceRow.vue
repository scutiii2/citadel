<script setup lang="ts">
// One uploaded file: page range (PDF) or fit (image), rotate, copy ID, remove.
import CopyButton from '../CopyButton.vue'
import ActionButton from '../ActionButton.vue'
import type { Fit } from '../../api/pdfMergerTypes'
import { formatBytes, plural } from '../../lib/pdfMerger/format'
import type { SourceState } from '../../stores/pdfMerger/files'

defineProps<{ source: SourceState }>()
const emit = defineEmits<{
  range: [string]
  rotate: []
  fit: [Fit | null]
  remove: []
  dragstart: [DragEvent]
  dragend: []
}>()
function onRange(event: Event): void {
  emit('range', (event.target as HTMLInputElement).value)
}

function onFit(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  emit('fit', value === '' ? null : (value as Fit))
}
</script>

<template>
  <div class="source-row">
    <span class="handle" aria-hidden="true" draggable="true" @dragstart="emit('dragstart', $event)" @dragend="emit('dragend')">⋮⋮</span>
    <span class="kind" :class="source.info.kind">{{ source.info.kind === 'pdf' ? 'PDF' : 'IMG' }}</span>
    <div class="meta">
      <div class="name" :title="source.info.name">{{ source.info.name }}</div>
      <div class="muted small">
        {{ plural(source.info.pages, 'page') }} · {{ formatBytes(source.info.size)
        }}<template v-if="source.rotate"> · rotated {{ source.rotate }}°</template>
      </div>
    </div>
    <div class="control">
      <template v-if="source.info.kind === 'pdf'">
        <input
          class="range"
          :class="{ invalid: source.rangeError }"
          :value="source.range"
          aria-label="Pages"
          placeholder="all"
          @input="onRange"
        />
        <div v-if="source.rangeError" class="error small" role="alert">{{ source.rangeError }}</div>
      </template>
      <select v-else aria-label="Image fit" :value="source.fit ?? ''" @change="onFit">
        <option value="">Default fit</option>
        <option value="fit">Fit page</option>
        <option value="fill">Fill page</option>
        <option value="original">Original size</option>
      </select>
    </div>
    <button type="button" class="icon" aria-label="Rotate" title="Rotate 90°" @click="emit('rotate')">⟳</button>
    <CopyButton :text="source.info.file_id" label="Copy file ID for chat" />
    <ActionButton icon="clear" class="danger" aria-label="Remove file" @click="emit('remove')">Remove</ActionButton>
  </div>
</template>
