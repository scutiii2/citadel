import { afterEach, describe, expect, it, vi } from 'vitest'
import { videoDownloaderClient as api, watchVideoJob } from './VideoDownloaderClient'
import { ApiError, onUnauthorized } from './http'
import type { JobStatus } from './VideoDownloaderTypes'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); onUnauthorized(() => {}) })
describe('video downloader client', () => {
  it('uses authenticated same-origin JSON and encodes opaque IDs', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    await api.cancelJob('a/b')
    expect(fetcher).toHaveBeenCalledWith('/api/video-downloader/jobs/a%2Fb/cancel', expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: '{}', headers: { 'Content-Type': 'application/json' } }))
    await api.deleteFile('a/b')
    expect(fetcher).toHaveBeenLastCalledWith('/api/video-downloader/files/a%2Fb', expect.objectContaining({ method: 'DELETE' }))
  })
  it('preserves error codes and invokes the session handler on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Protected', error: { code: 'drm_protected', message: 'Protected' } }), { status: 422 })).mockResolvedValueOnce(new Response('{}', { status: 401 })))
    await expect(api.probe('https://example.com')).rejects.toMatchObject({ status: 422, code: 'drm_protected', message: 'Protected' })
    const unauthorized = vi.fn()
    onUnauthorized(unauthorized)
    await expect(api.listFiles()).rejects.toBeInstanceOf(ApiError)
    expect(unauthorized).toHaveBeenCalledOnce()
  })
  it('polls long downloads beyond ten successes and stops at completion', async () => {
    vi.useFakeTimers()
    const status: JobStatus = { job_id: 'j', state: 'downloading', percent: 5, speed: null, eta: null, file: null, error: null }
    const get = vi.spyOn(api, 'getJobStatus').mockResolvedValue(status)
    const update = vi.fn()
    const stop = watchVideoJob('j', update, vi.fn())
    await vi.advanceTimersByTimeAsync(22_000)
    expect(get.mock.calls.length).toBeGreaterThan(10)
    get.mockResolvedValue({ ...status, state: 'done' })
    await vi.advanceTimersByTimeAsync(2000)
    const calls = get.mock.calls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(get).toHaveBeenCalledTimes(calls)
    stop()
    get.mockRestore()
  })
  it('ignores an in-flight poll after its watcher stops', async () => {
    let resolve!: (s: JobStatus) => void
    const get = vi.spyOn(api, 'getJobStatus').mockReturnValue(new Promise(r => { resolve = r }))
    const update = vi.fn()
    const stop = watchVideoJob('j', update, vi.fn())
    stop()
    resolve({ job_id: 'j', state: 'error', percent: null, speed: null, eta: null, file: null, error: null })
    await Promise.resolve()
    expect(update).not.toHaveBeenCalled()
    get.mockRestore()
  })
  it('retries temporary failures but stops when a job is gone', async () => {
    vi.useFakeTimers()
    const get = vi.spyOn(api, 'getJobStatus').mockRejectedValueOnce(new ApiError(503, 'Unavailable')).mockRejectedValueOnce(new ApiError(404, 'Job not found'))
    const fail = vi.fn()
    watchVideoJob('j', vi.fn(), fail)
    await vi.advanceTimersByTimeAsync(0)
    expect(fail).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2000)
    expect(fail).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(get).toHaveBeenCalledTimes(2)
    get.mockRestore()
  })
})
