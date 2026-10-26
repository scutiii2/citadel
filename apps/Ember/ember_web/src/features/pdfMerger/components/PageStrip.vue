<script setup lang="ts">
// Every output page in order. Dragging a page switches the plan to manual order.
import { computed } from 'vue'
import { useReorder } from '../../../composables/useReorder'
import { plural } from '../../../utils/format'
import { useFilesStore } from '../stores/files'
import { usePlanStore } from '../stores/plan'
import PageThumb from './PageThumb.vue'

const files = useFilesStore()
const plan = usePlanStore()
const { dragFrom, onDragStart, onDragEnd, onDragOver, onDrop, onKey } = useReorder({
  move: (from, to) => plan.movePage(from, to),
  count: () => plan.pages.length,
  keys: { back: 'ArrowLeft', forward: 'ArrowRight' },
})
const infoById = computed(() => new Map(files.sources.map((s) => [s.info.file_id, s.info])))

function label(fileId: string, page: number): string {
  const info = infoById.value.get(fileId)
  if (!info) return ''
  const name = info.name.replace(/\.[^.]+$/, '')
  return info.kind === 'image' ? name : `${name} p${page + 1}`
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
        @dragend="onDragEnd"
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
