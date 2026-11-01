import { apiRequest } from '../../../api/http'
import { pollJob } from '../../../api/pollJob'
import type { FileInfo, JobStatus, ProbeResult, MediaPackage } from './MediaDownloaderTypes'

const BASE = '/api/media-downloader'
const id = encodeURIComponent

export const mediaDownloaderClient = {
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
  return pollJob({
    fetch: () => mediaDownloaderClient.getJobStatus(jobId),
    onStatus: (status) => {
      update(status)
      return status.state === 'done' || status.state === 'error'
    },
    onFail: fail,
    intervalMs: 2000,
    maxFailures: 10,
  })
}
