// Uploaded source files and their per-file options (range, rotation, fit).
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useAuthStore } from '../../../stores/auth'
import { forgetDocument } from '../lib/pdfThumbs'
import * as api from '../api/PdfMergerClient'
import type { FileInfo, Fit, Rotation } from '../api/pdfMergerTypes'
import { errorMessage } from '../../../utils/errors'
import { moveItem, parseRange } from '../lib/segments'

export interface SourceState {
  info: FileInfo
  /** What the user typed. */
  range: string
  /** Last valid selection, 0-based. */
  pages: number[]
  rangeError: string | null
  rotate: Rotation
  /** Images only; null = use the output default. */
  fit: Fit | null
}

function allPages(info: FileInfo): number[] {
  return Array.from({ length: info.pages }, (_, i) => i)
}

export const useFilesStore = defineStore('pdfMergerFiles', () => {
  const auth = useAuthStore()
  let generation = 0
  const sources = ref<SourceState[]>([])
  const uploading = ref(0)
  const errors = ref<string[]>([])

  function find(fileId: string): SourceState | undefined {
    return sources.value.find((s) => s.info.file_id === fileId)
  }

  function add(info: FileInfo): void {
    if (find(info.file_id)) return
    sources.value.push({ info, range: 'all', pages: allPages(info), rangeError: null, rotate: 0, fit: null })
  }

  /** One at a time, so sources appear in drop order. */
  async function upload(files: readonly File[]): Promise<void> {
    const current = generation
    uploading.value += files.length
    for (const file of files) {
      if (current !== generation) return
      try {
        const info = await api.uploadFile(file)
        if (current === generation) add(info)
      } catch (error) {
        if (current === generation) errors.value.push(`${file.name}: ${errorMessage(error)}`)
      } finally {
        if (current === generation) uploading.value -= 1
      }
    }
  }

  /** Bring back this browser's files after a reload. Also makes the server set the session cookie. */
  async function restore(): Promise<void> {
    const current = generation
    try {
      const infos = await api.listFiles()
      if (current !== generation) return
      for (const info of infos) add(info)
    } catch (error) {
      if (current === generation) errors.value.push(`Couldn't load your files: ${errorMessage(error)}`)
    }
  }

  async function remove(fileId: string): Promise<void> {
    const current = generation
    try {
      await api.deleteFile(fileId)
      if (current !== generation) return
      sources.value = sources.value.filter((s) => s.info.file_id !== fileId)
      forgetDocument(api.contentUrl(fileId))
    } catch (error) {
      if (current === generation) errors.value.push(`Couldn't remove the file: ${errorMessage(error)}`)
    }
  }

  function stop(): void { generation++; uploading.value = 0 }

  watch(() => auth.account?.id, () => {
    generation++
    for (const source of sources.value) forgetDocument(api.contentUrl(source.info.file_id))
    sources.value = []; uploading.value = 0; errors.value = []
  }, { flush: 'sync' })

  function setRange(fileId: string, text: string): void {
    const source = find(fileId)
    if (!source) return
    source.range = text
    const parsed = parseRange(text, source.info.pages)
    if (typeof parsed === 'string') {
      source.rangeError = parsed
    } else {
      source.rangeError = null
      source.pages = parsed
    }
  }

  function rotate(fileId: string): void {
    const source = find(fileId)
    if (source) source.rotate = ((source.rotate + 90) % 360) as Rotation
  }

  function setFit(fileId: string, fit: Fit | null): void {
    const source = find(fileId)
    if (source) source.fit = fit
  }

  function moveSource(from: number, to: number): void {
    sources.value = moveItem(sources.value, from, to)
  }

  function dismissError(index: number): void {
    errors.value.splice(index, 1)
  }

  return { stop, sources, uploading, errors, add, upload, restore, remove, setRange, rotate, setFit, moveSource, dismissError }
})
