import { apiRequest, ApiError } from './http'
import type { FileInfo, JobStatus, ProbeResult, MediaPackage } from './VideoDownloaderTypes'

const BASE = '/api/video-downloader'
const id = encodeURIComponent

export const videoDownloaderClient = {
  probe: (url: string) => apiRequest<ProbeResult>('POST', `${BASE}/probe`, { url }),
  startDownload: (url: string, preset: string) => apiRequest<{ job_id: string }>('POST', `${BASE}/downloads`, { url, preset }),
  getJobStatus: (jobId: string) => apiRequest<JobStatus>('GET', `${BASE}/jobs/${id(jobId)}`),
  cancelJob: (jobId: string) => apiRequest<void>('POST', `${BASE}/jobs/${id(jobId)}/cancel`, {}),
  listFiles: () => apiRequest<FileInfo[]>('GET', `${BASE}/files`),
  deleteFile: (fileId: string) => apiRequest<void>('DELETE', `${BASE}/files/${id(fileId)}`),
  listPackages: () => apiRequest<MediaPackage[]>('GET', `${BASE}/packages`),
  createPackage: (name: string) => apiRequest<MediaPackage>('POST', `${BASE}/packages`, { name }),
  deletePackage: (packageId: string) => apiRequest<void>('DELETE', `${BASE}/packages/${id(packageId)}`),
  addPackageItem: (packageId: string, url: string, preset: string) => apiRequest<MediaPackage>('POST', `${BASE}/packages/${id(packageId)}/items`, { url, preset }),
  removePackageItem: (packageId: string, itemId: string) => apiRequest<MediaPackage>('DELETE', `${BASE}/packages/${id(packageId)}/items/${id(itemId)}`),
  startPackage: (packageId: string) => apiRequest<{ job_id: string }>('POST', `${BASE}/packages/${id(packageId)}/start`, {}),
}

/** Poll without overlapping requests. Stopping also discards a response already in flight. */
export function watchVideoJob(jobId: string, update: (status: JobStatus) => void, fail: (error: unknown) => void): () => void {
  let stopped = false
  let failures = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  const stop = () => {
    stopped = true
    clearTimeout(timer)
  }
  const poll = async () => {
    try {
      const status = await videoDownloaderClient.getJobStatus(jobId)
      if (stopped) return
      failures = 0
      update(status)
      if (status.state === 'done' || status.state === 'error') return stop()
    } catch (error) {
      if (stopped) return
      failures++
      if ((error instanceof ApiError && error.status < 500) || failures >= 10) {
        stop()
        fail(error)
        return
      }
    }
    if (!stopped) timer = setTimeout(() => void poll(), 2000)
  }
  void poll()
  return stop
}
