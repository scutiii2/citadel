/** Account-scoped JSON requests through ember_api. */
import { apiRequest } from '../../../api/http'
import { pollJob } from '../../../api/pollJob'
import { toBase64 } from '../../../api/files/AttachmentsClient'
import type { FileInfo, JobEvent, MergePlan, MergeResult } from './pdfMergerTypes'
const BASE = '/api/pdf-merger'
export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024
function fileUrl(id: string, suffix = ''): string { return `${BASE}/files/${encodeURIComponent(id)}${suffix}` }
export function contentUrl(id: string): string { return fileUrl(id, '/content') }
export function downloadUrl(id: string): string { return fileUrl(id, '/download') }
export function listFiles(): Promise<FileInfo[]> { return apiRequest('GET', `${BASE}/files`) }
export async function uploadFile(file: File): Promise<FileInfo> {
  if (file.size > MAX_UPLOAD_BYTES) throw new Error('Files must be 15 MiB or smaller.')
  const data = await toBase64(file)
  return apiRequest('POST', `${BASE}/files`, { filename: file.name, data })
}
export function deleteFile(id: string): Promise<void> { return apiRequest('DELETE', fileUrl(id)) }
export function startMerge(plan: MergePlan): Promise<{job_id: string}> { return apiRequest('POST', `${BASE}/merge`, plan) }
export function cancelJob(id: string): Promise<void> { return apiRequest('POST', `${BASE}/jobs/${encodeURIComponent(id)}/cancel`, {}) }
interface JobStatus {
  job_id: string
  state: 'queued' | 'progress' | 'done' | 'error'
  done: number
  total: number
  result: MergeResult | null
  error: {code: string; message: string} | null
}
/** Sequential polling; stop also guards responses already in flight. */
export function watchJob(id: string, onEvent: (event: JobEvent) => void): () => void {
  return pollJob<JobStatus>({
    fetch: () => apiRequest('GET', `${BASE}/jobs/${encodeURIComponent(id)}`),
    onStatus: (job) => {
      if (job.state === 'done' && job.result) { onEvent({ ...job.result, type: 'done', download_url: downloadUrl(job.result.file_id) }); return true }
      if (job.state === 'error') { onEvent({type: 'error', code: job.error?.code ?? 'merge_failed', message: job.error?.message ?? 'Merge failed.'}); return true }
      onEvent({type: 'progress', done: job.done, total: job.total})
      return false
    },
    onFail: (error) => onEvent({type: 'error', code: 'connection_lost', message: error instanceof Error ? error.message : 'Could not check merge progress.'}),
    intervalMs: 750,
    maxFailures: 1,
  })
}
