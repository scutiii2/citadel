import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mediaDownloaderClient as api, watchVideoJob } from '../api/MediaDownloaderClient'
import type { FileInfo, JobStatus, ProbeResult } from '../api/MediaDownloaderTypes'
import { ApiError } from '../../../api/http'
import { useMediaDownloaderStore } from './mediaDownloader'
import { useAuthStore } from '../../../stores/auth'

vi.mock('../api/MediaDownloaderClient', () => ({ mediaDownloaderClient: { probe: vi.fn(), listFiles: vi.fn(), startDownload: vi.fn(), cancelJob: vi.fn(), deleteFile: vi.fn() }, watchVideoJob: vi.fn() }))
const file: FileInfo = { file_id: 'f', name: 'a.mp4', kind: 'video', mime: 'video/mp4', size: 10, duration: 5, expires_at: 99, download_url: '/api/media-downloader/files/f/download' }
const probe: ProbeResult = { url: 'https://example.com/v', title: 'Video', thumbnail: null, duration: 10, uploader: null, options: [{ id: 'best', label: 'Best', kind: 'video', estimated_bytes: null, blocked: true, code: 'too_large', reason: 'Too large' }, { id: '720p', label: '720p', kind: 'video', estimated_bytes: 100, blocked: false, code: null, reason: null }] }
let update: (status: JobStatus) => void
const stop = vi.fn()
beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  vi.mocked(api.probe).mockResolvedValue(probe)
  vi.mocked(api.startDownload).mockResolvedValue({ job_id: 'j' })
  vi.mocked(api.listFiles).mockResolvedValue([file])
  vi.mocked(watchVideoJob).mockImplementation((_id, fn) => { update = fn; return stop })
})
describe('media downloader state', () => {
  it('selects only available presets and displays readable error codes', async () => {
    const store = useMediaDownloaderStore()
    store.url = probe.url
    await store.check()
    expect(store.selected).toBe('720p')
    store.select('best')
    expect(store.selected).toBe('720p')
    vi.mocked(api.probe).mockRejectedValue(new ApiError(422, 'raw', 'drm_protected'))
    await store.check()
    expect(store.error).toContain('copy-protected')
  })
  it('discards a probe if the typed URL changes during the request', async () => {
    let resolve!: (p: ProbeResult) => void
    vi.mocked(api.probe).mockReturnValue(new Promise(r => { resolve = r }))
    const store = useMediaDownloaderStore()
    store.url = probe.url
    const check = store.check()
    store.url = 'https://example.com/other'
    resolve(probe)
    await check
    expect(store.result).toBeNull()
  })
  it('keeps progress monotonic, refreshes finished files, and reconnects after leaving', async () => {
    const store = useMediaDownloaderStore()
    store.activate()
    store.url = probe.url
    await store.check()
    await store.start()
    const status: JobStatus = { job_id: 'j', state: 'downloading', percent: 40, speed: 10, eta: 4, file: null, error: null }
    update(status)
    update({ ...status, percent: 10 })
    expect(store.jobs[0]?.percent).toBe(40)
    store.stopWatching()
    expect(stop).toHaveBeenCalled()
    update({ ...status, state: 'done', file })
    expect(store.jobs[0]?.state).toBe('downloading')
    store.activate()
    expect(watchVideoJob).toHaveBeenCalledTimes(2)
    update({ ...status, state: 'done', file })
    await Promise.resolve()
    expect(store.jobs[0]?.percent).toBe(100)
    expect(store.files).toEqual([file])
    store.stopWatching()
  })
  it('resets private state on account change and rejects stale start responses', async () => {
    const store = useMediaDownloaderStore()
    store.url = probe.url
    await store.check()
    let resolve!: (j: { job_id: string }) => void
    vi.mocked(api.startDownload).mockReturnValue(new Promise(r => { resolve = r }))
    const start = store.start()
    useAuthStore().account = { id: 2 } as NonNullable<ReturnType<typeof useAuthStore>['account']>
    resolve({ job_id: 'old' })
    await start
    expect(store.jobs).toEqual([])
    expect(store.result).toBeNull()
    expect(store.url).toBe('')
    expect(store.starting).toBe(false)
  })
  it('keeps files after a deletion failure and ignores an older list after deletion', async () => {
    const store = useMediaDownloaderStore()
    await store.refreshFiles()
    vi.mocked(api.deleteFile).mockRejectedValueOnce(new Error('Offline'))
    expect(await store.remove('f')).toBe(false)
    expect(store.files).toEqual([file])
    expect(store.filesError).toBe('Offline')
    let resolve!: (f: FileInfo[]) => void
    vi.mocked(api.listFiles).mockReturnValue(new Promise(r => { resolve = r }))
    const refresh = store.refreshFiles()
    vi.mocked(api.deleteFile).mockResolvedValue()
    expect(await store.remove('f')).toBe(true)
    resolve([file])
    await refresh
    expect(store.files).toEqual([])
  })
})
