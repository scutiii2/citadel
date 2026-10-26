<script setup lang="ts">
// Every output page in order. Dragging a page switches the plan to manual order.
import { computed, ref } from 'vue'
import { plural } from '../../../utils/format'
import { useFilesStore } from '../stores/files'
import { usePlanStore } from '../stores/plan'
import PageThumb from './PageThumb.vue'

const files = useFilesStore()
const plan = usePlanStore()
const dragFrom = ref<number | null>(null)
const infoById = computed(() => new Map(files.sources.map((s) => [s.info.file_id, s.info])))

function label(fileId: string, page: number): string {
  const info = infoById.value.get(fileId)
  if (!info) return ''
  const name = info.name.replace(/\.[^.]+$/, '')
  return info.kind === 'image' ? name : `${name} p${page + 1}`
}

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
  if (!event.altKey || (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight')) return
  event.preventDefault()
  const to = event.key === 'ArrowLeft' ? index - 1 : index + 1
  if (to >= 0 && to < plan.pages.length) plan.movePage(index, to)
}

function onDrop(index: number): void {
  if (dragFrom.value !== null) plan.movePage(dragFrom.value, index)
  dragFrom.value = null
}
</script>

<template>
  <section v-if="plan.pages.length" class="panel">
    <div class="panel-head">
      <h2>Page order <span class="muted small">{{ plural(plan.pages.length, 'page') }}</span></h2>
      <button v-if="plan.manualOrder" type="button" class="link" @click="plan.resetOrder()">Reset order</button>
    </div>
    <p class="page-hint">Drag pages or use the arrows. Your PDF follows this order.</p>
    <ol class="strip" aria-label="Pages. Press Alt and an arrow key to move a page.">
      <li
        v-for="(item, index) in plan.pages"
        :key="item.key"
        draggable="true"
        tabindex="0"
        :class="{ dragging: dragFrom === index }"
        @dragstart="onDragStart(index, $event)"
        @dragend="dragFrom = null"
        @keydown="onKey(index, $event)"
        @dragover.prevent="onDragOver"
        @drop.prevent="onDrop(index)"
      >
        <PageThumb :item="item" :kind="infoById.get(item.fileId)?.kind ?? 'pdf'" :label="label(item.fileId, item.page)" />
        <div class="page-moves">
          <button type="button" :aria-label="`Move ${label(item.fileId, item.page)} earlier`" :disabled="index === 0" @click="plan.movePage(index, index - 1)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6" /></svg></button>
          <button type="button" :aria-label="`Move ${label(item.fileId, item.page)} later`" :disabled="index === plan.pages.length - 1" @click="plan.movePage(index, index + 1)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6" /></svg></button>
        </div>
      </li>
    </ol>
  </section>
</template>
