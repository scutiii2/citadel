<script setup lang="ts">
// One uploaded file: page range (PDF) or fit (image), rotate, copy ID, remove.
import CopyButton from '../CopyButton.vue'
import ActionButton from '../ActionButton.vue'
import { ref, watch } from 'vue'
import type { Fit } from '../../api/pdfMergerTypes'
import { formatBytes, plural } from '../../lib/pdfMerger/format'
import type { SourceState } from '../../stores/pdfMerger/files'

const props = defineProps<{ source: SourceState; canMoveUp?: boolean; canMoveDown?: boolean }>()
const expanded = ref(!!props.source.rangeError)
watch(() => props.source.rangeError, error => { if (error) expanded.value = true })
const emit = defineEmits<{
  range: [string]
  rotate: []
  fit: [Fit | null]
  remove: []
  moveUp: []
  moveDown: []
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
  <div class="source-item"><div class="source-row">
    <span class="handle" aria-hidden="true" draggable="true" @dragstart="emit('dragstart', $event)" @dragend="emit('dragend')">⋮⋮</span>
    <span class="kind" :class="source.info.kind">{{ source.info.kind === 'pdf' ? 'PDF' : 'IMG' }}</span>
    <div class="meta">
      <div class="name" :title="source.info.name">{{ source.info.name }}</div>
      <div class="muted small">
        {{ plural(source.info.pages, 'page') }} · {{ formatBytes(source.info.size)
        }}<template v-if="source.rotate"> · rotated {{ source.rotate }}°</template>
      </div>
    </div>
  </div>
  <details class="source-options" :open="expanded" @toggle="expanded = ($event.target as HTMLDetailsElement).open">
    <summary :aria-label="`File options for ${source.info.name}`">File options<span v-if="source.rangeError" class="error"> · Fix pages</span></summary>
    <div class="source-controls"><div class="control">
      <template v-if="source.info.kind === 'pdf'">
        <label>Pages<input
          class="range"
          :class="{ invalid: source.rangeError }"
          :value="source.range"
          aria-label="Pages"
          placeholder="all"
          @input="onRange"
        /></label>
        <div v-if="source.rangeError" class="error small" role="alert">{{ source.rangeError }}</div>
      </template>
      <label v-else>Image fit<select aria-label="Image fit" :value="source.fit ?? ''" @change="onFit">
        <option value="">Default fit</option>
        <option value="fit">Fit page</option>
        <option value="fill">Fill page</option>
        <option value="original">Original size</option>
      </select></label>
    </div>
    <button type="button" class="rotate" aria-label="Rotate" title="Rotate 90°" @click="emit('rotate')">⟳ {{ source.rotate }}°</button></div>
    <div class="file-actions"><button type="button" :aria-label="`Move ${source.info.name} earlier`" :disabled="!canMoveUp" @click="emit('moveUp')">↑ Earlier</button><button type="button" :aria-label="`Move ${source.info.name} later`" :disabled="!canMoveDown" @click="emit('moveDown')">↓ Later</button><CopyButton :text="source.info.file_id" label="Copy file ID for chat" /></div>
    <div class="danger-zone"><span>Remove this source</span><ActionButton icon="clear" class="danger" aria-label="Remove file" @click="emit('remove')">Remove</ActionButton></div>
  </details></div>
</template>
<style scoped>
.source-item { min-width: 0; }
.source-row { display: flex; align-items: center; gap: 8px; }
.handle { color: var(--muted); cursor: grab; }
.kind { font-size: .6em; color: var(--muted); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 2px 4px; }
.meta { flex: 1; min-width: 0; }
.name { font-size: .85em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.small { font-size: .7em; margin-top: 3px; color: var(--muted); }
.source-options { margin-top: 10px; font-size: .8em; }
summary { color: var(--muted); cursor: pointer; padding-block: 5px; }
.source-controls { display: flex; align-items: end; gap: 8px; margin-top: 10px; }
.control { flex: 1; min-width: 0; }
label { color: var(--muted); display: grid; gap: 5px; }
input, select { min-width: 0; width: 100%; font: inherit; background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 8px; }
input.invalid { border-color: var(--danger); }
button { font: inherit; padding: 7px 10px; border: 1px solid var(--border); border-radius: var(--radius-full); color: var(--text); background: var(--bg); cursor: pointer; }
.rotate { min-height: 36px; }
.error { color: var(--danger); }
.file-actions { display: flex; align-items: center; gap: 6px; margin-top: 12px; flex-wrap: wrap; }
.danger-zone { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-top: 16px; padding: 10px; border: 1px solid var(--danger); border-radius: var(--radius-lg); }
button.danger { color: var(--danger); border-color: var(--danger); }
.danger-zone :deep(.label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
:is(button, input, select, summary):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button:disabled { opacity: .5; cursor: not-allowed; }
@media (max-width: 767px) { button, input, select, summary { min-height: 44px; } }
</style>
