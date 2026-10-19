import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { videoDownloaderClient as api, watchVideoJob } from '../api/VideoDownloaderClient'
import type { FileInfo, JobState, JobStatus, ProbeResult } from '../api/VideoDownloaderTypes'
import { ApiError } from '../api/http'
import { friendlyError, messageOf } from '../utils/videoDownloader/messages'
import { useAuthStore } from './auth'

export interface VideoJob {
  id: string
  title: string
  presetLabel: string
  state: JobState
  percent: number | null
  speed: number | null
  eta: number | null
  file: FileInfo | null
  error: { code: string; message: string } | null
  startedAt: number
}

export function videoError(error: unknown): string {
  return error instanceof ApiError ? friendlyError(error.code ?? '', error.message) : messageOf(error)
}

export const useVideoDownloaderStore = defineStore('videoDownloader', () => {
  const auth = useAuthStore()
  const url = ref('')
  const result = ref<ProbeResult | null>(null)
  const selected = ref<string | null>(null)
  const checking = ref(false)
  const starting = ref(false)
  const loadingFiles = ref(false)
  const error = ref<string | null>(null)
  const filesError = ref<string | null>(null)
  const files = ref<FileInfo[]>([])
  const jobs = ref<VideoJob[]>([])
  const cancelling = ref<string[]>([])
  const removing = ref<string[]>([])
  const selectedOption = computed(() => result.value?.options.find(o => o.id === selected.value && !o.blocked) ?? null)
  const canCheck = computed(() => !!url.value.trim() && !checking.value)
  const stops = new Map<string, () => void>()
  let epoch = 0
  let probeRequest = 0
  let fileRequest = 0
  let active = false

  function stopWatching(): void {
    active = false
    epoch++
    probeRequest++
    fileRequest++
    checking.value = starting.value = loadingFiles.value = false
    cancelling.value = []
    removing.value = []
    stops.forEach(stop => stop())
    stops.clear()
  }

  function reset(): void {
    stopWatching()
    url.value = ''
    result.value = null
    selected.value = null
    error.value = filesError.value = null
    jobs.value = []
    files.value = []
  }
  watch(() => auth.account?.id, reset, { flush: 'sync' })
  watch(url, () => {
    probeRequest++
    checking.value = false
    result.value = null
    selected.value = null
  }, { flush: 'sync' })

  async function check(): Promise<void> {
    if (!canCheck.value) return
    const request = ++probeRequest
    const generation = epoch
    checking.value = true
    error.value = null
    result.value = null
    selected.value = null
    try {
      const response = await api.probe(url.value.trim())
      if (generation !== epoch || request !== probeRequest) return
      result.value = response
      selected.value = response.options.find(o => !o.blocked)?.id ?? null
    } catch (e) {
      if (generation === epoch && request === probeRequest) error.value = videoError(e)
    } finally {
      if (generation === epoch && request === probeRequest) checking.value = false
    }
  }

  function select(id: string): void {
    if (result.value?.options.some(o => o.id === id && !o.blocked)) selected.value = id
  }

  async function refreshFiles(): Promise<void> {
    const request = ++fileRequest
    const generation = epoch
    loadingFiles.value = true
    try {
      const response = await api.listFiles()
      if (generation !== epoch || request !== fileRequest) return
      files.value = response
      filesError.value = null
    } catch (e) {
      if (generation === epoch && request === fileRequest) filesError.value = videoError(e)
    } finally {
      if (generation === epoch && request === fileRequest) loadingFiles.value = false
    }
  }

  function follow(job: VideoJob): void {
    const generation = epoch
    if (!active || stops.has(job.id) || ['done', 'error'].includes(job.state)) return
    stops.set(job.id, watchVideoJob(job.id, (status: JobStatus) => {
      if (generation !== epoch || !active) return
      const current = jobs.value.find(j => j.id === job.id)
      if (!current) return
      current.state = status.state
      if (status.percent !== null) current.percent = Math.max(current.percent ?? 0, status.percent)
      current.speed = status.speed
      current.eta = status.eta
      current.file = status.file
      current.error = status.error ? { ...status.error, message: friendlyError(status.error.code, status.error.message) } : status.state === 'error' ? { code: 'http_error', message: 'The download failed. Try again.' } : null
      if (status.state === 'done' || status.state === 'error') stops.delete(job.id)
      if (status.state === 'done') {
        current.percent = 100
        void refreshFiles()
      }
    }, e => {
      if (generation !== epoch || !active) return
      stops.delete(job.id)
      error.value = `Could not follow this download: ${videoError(e)} Reopen this page to reconnect.`
    }))
  }

  function activate(): void {
    if (active) return
    active = true
    void refreshFiles()
    jobs.value.forEach(follow)
  }

  async function start(): Promise<void> {
    const source = result.value
    const option = selectedOption.value
    if (!source || !option || starting.value) return
    const generation = epoch
    const request = probeRequest
    starting.value = true
    error.value = null
    try {
      const response = await api.startDownload(source.url, option.id)
      if (generation !== epoch) return
      jobs.value.unshift({ id: response.job_id, title: source.title, presetLabel: option.label, state: 'queued', percent: null, speed: null, eta: null, file: null, error: null, startedAt: Date.now() })
      follow(jobs.value[0]!)
      if (request === probeRequest) {
        url.value = ''
        result.value = null
        selected.value = null
      }
    } catch (e) {
      if (generation === epoch) error.value = videoError(e)
    } finally {
      if (generation === epoch) starting.value = false
    }
  }

  async function cancel(id: string): Promise<boolean> {
    if (cancelling.value.includes(id)) return false
    const generation = epoch
    cancelling.value.push(id)
    error.value = null
    try {
      await api.cancelJob(id)
      return generation === epoch
    } catch (e) {
      if (generation === epoch) error.value = videoError(e)
      return false
    } finally {
      if (generation === epoch) cancelling.value = cancelling.value.filter(x => x !== id)
    }
  }

  async function remove(id: string): Promise<boolean> {
    if (removing.value.includes(id)) return false
    const generation = epoch
    removing.value.push(id)
    filesError.value = null
    try {
      await api.deleteFile(id)
      if (generation !== epoch) return false
      // Invalidate a list fetch started before deletion.
      fileRequest++
      loadingFiles.value = false
      files.value = files.value.filter(f => f.file_id !== id)
      jobs.value.forEach(job => { if (job.file?.file_id === id) job.file = null })
      filesError.value = null
      return true
    } catch (e) {
      if (generation === epoch) filesError.value = videoError(e)
      return false
    } finally {
      if (generation === epoch) removing.value = removing.value.filter(x => x !== id)
    }
  }

  function dismiss(id: string): void {
    stops.get(id)?.()
    stops.delete(id)
    jobs.value = jobs.value.filter(j => j.id !== id)
  }

  return { url, result, selected, checking, starting, loadingFiles, error, filesError, files, jobs, cancelling, removing, selectedOption, canCheck, check, select, start, refreshFiles, cancel, remove, dismiss, activate, stopWatching, reset }
})
