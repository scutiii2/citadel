import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { uploadFile, watchJob, cancelJob, MAX_UPLOAD_BYTES } from './PdfMergerClient'
import { apiRequest } from '../../../api/http'
vi.mock('../../../api/http', () => ({apiRequest: vi.fn()}))
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })
describe('PDF merger client', () => {
  it('uploads JSON base64 through ember_api', async () => {
    await uploadFile(new File(['PDF'], 'example.pdf'))
    expect(apiRequest).toHaveBeenCalledWith('POST','/api/pdf-merger/files',{filename:'example.pdf',data:'UERG'})
  })
  it('refuses files larger than 15 MiB before reading', async () => {
    const file = new File(['x'], 'large.pdf')
    Object.defineProperty(file,'size',{value:MAX_UPLOAD_BYTES + 1})
    await expect(uploadFile(file)).rejects.toThrow('15 MiB')
    expect(apiRequest).not.toHaveBeenCalled()
  })
  it('adapts done status and constructs a safe local download path', async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({state:'done',result:{file_id:'result',download_url:'https://untrusted.invalid/file'}})
    const event = vi.fn()
    watchJob('job',event)
    await flushPromises()
    expect(event).toHaveBeenCalledWith(expect.objectContaining({type:'done',download_url:'/api/pdf-merger/files/result/download'}))
  })
  it('ignores in-flight responses after stopping', async () => {
    let resolve!: (value: unknown) => void
    vi.mocked(apiRequest).mockReturnValueOnce(new Promise(r => {resolve=r}))
    const event = vi.fn()
    const stop = watchJob('job',event)
    stop(); resolve({state:'progress',done:1,total:2})
    await flushPromises()
    expect(event).not.toHaveBeenCalled()
  })
  it('sends a JSON cancellation body', async () => {
    await cancelJob('job')
    expect(apiRequest).toHaveBeenCalledWith('POST','/api/pdf-merger/jobs/job/cancel',{})
  })
})
