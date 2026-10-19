// Output page order, output options and the merge job's state.
import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'
import * as api from '../../api/PdfMergerClient'
import type { FileKind, Fit, JobEvent, MergePlan, MergeResult, OutputOptions } from '../../api/pdfMergerTypes'
import { messageOf } from '../../lib/pdfMerger/messages'
import { moveItem, pageKey, reconcile, toSegments, type PageItem } from '../../lib/pdfMerger/segments'
import { useAuthStore } from '../auth'
import { useFilesStore } from './files'

export type MergeStatus = 'idle' | 'running' | 'done' | 'error'

export const usePlanStore = defineStore('pdfMergerPlan', () => {
  const files = useFilesStore()
  const auth = useAuthStore()
  let generation = 0
  let jobId: string | null = null
  const startedAt = ref(0)

  const pages = ref<PageItem[]>([])
  const manualOrder = ref(false)
  const output = reactive<OutputOptions>({
    filename: 'merged.pdf',
    title: null,
    author: null,
    bookmarks: true,
    image_page_size: 'A4',
    image_fit: 'fit',
    image_margin_mm: 10,
  })
  const status = ref<MergeStatus>('idle')
  const progress = ref({ done: 0, total: 0 })
  const result = ref<MergeResult | null>(null)
  const error = ref<string | null>(null)
  let stopWatching: (() => void) | null = null

  /** Pages in source order, from each source's current selection and rotation. */
  function freshPages(): PageItem[] {
    return files.sources.flatMap((source) =>
      source.pages.map((page) => ({
        key: pageKey(source.info.file_id, page),
        fileId: source.info.file_id,
        page,
        rotate: source.rotate,
      })),
    )
  }

  watch(
    freshPages,
    (fresh) => {
      pages.value = manualOrder.value ? reconcile(pages.value, fresh) : fresh
    },
    { immediate: true },
  )

  const segments = computed(() =>
    toSegments(
      pages.value,
      new Map<string, Fit | null>(files.sources.map((s) => [s.info.file_id, s.fit])),
      new Map<string, FileKind>(files.sources.map((s) => [s.info.file_id, s.info.kind])),
    ),
  )
  const hasRangeErrors = computed(() => files.sources.some((s) => s.rangeError !== null))
  const canMerge = computed(() => pages.value.length > 0 && status.value !== 'running' && !hasRangeErrors.value)

  function movePage(from: number, to: number): void {
    if (from === to) return
    pages.value = moveItem(pages.value, from, to)
    manualOrder.value = true
  }

  function resetOrder(): void {
    manualOrder.value = false
    pages.value = freshPages()
  }

  function buildPlan(): MergePlan {
    return {
      segments: segments.value,
      output: {
        ...output,
        filename: output.filename.trim() || 'merged.pdf',
        title: output.title?.trim() || null,
        author: output.author?.trim() || null,
      },
    }
  }

  function onEvent(event: JobEvent): void {
    if (event.type === 'progress') {
      progress.value = { done: event.done, total: event.total }
    } else if (event.type === 'done') {
      result.value = {
        file_id: event.file_id,
        name: event.name,
        pages: event.pages,
        size: event.size,
        expires_at: event.expires_at,
        download_url: event.download_url,
      }
      status.value = 'done'
      stopWatching = null
    } else if (event.type === 'error') {
      error.value = event.message
      status.value = 'error'
      stopWatching = null
    }
  }

  async function merge(): Promise<void> {
    if (!canMerge.value) return
    stopWatching?.()
    const current = ++generation
    jobId = null
    startedAt.value = Date.now()
    status.value = 'running'
    error.value = null
    result.value = null
    progress.value = { done: 0, total: pages.value.length }
    try {
      const { job_id } = await api.startMerge(buildPlan())
      if (current !== generation) return
      jobId = job_id
      stopWatching = api.watchJob(job_id, (event) => { if (current === generation) onEvent(event) })
    } catch (caught) {
      if (current !== generation) return
      error.value = messageOf(caught)
      status.value = 'error'
    }
  }

  function stop(): void {
    generation++
    stopWatching?.(); stopWatching = null
    if (status.value === 'running') status.value = 'idle'
  }
  async function cancel(): Promise<void> {
    if (!jobId) return
    const current = generation
    try {
      await api.cancelJob(jobId)
      if (current !== generation) return
      stop(); error.value = 'Merge cancelled.'; status.value = 'error'
    } catch (caught) { if (current === generation) error.value = messageOf(caught) }
  }
  watch(() => auth.account?.id, () => {
    stop(); status.value = 'idle'; pages.value = []; manualOrder.value = false; result.value = null; error.value = null; jobId = null
    progress.value = {done: 0, total: 0}
    Object.assign(output, {filename: 'merged.pdf', title: null, author: null, bookmarks: true, image_page_size: 'A4', image_fit: 'fit', image_margin_mm: 10})
  }, {flush: 'sync'})

  return {
    stop, cancel, startedAt,
    pages,
    manualOrder,
    output,
    status,
    progress,
    result,
    error,
    segments,
    hasRangeErrors,
    canMerge,
    movePage,
    resetOrder,
    buildPlan,
    merge,
  }
})
