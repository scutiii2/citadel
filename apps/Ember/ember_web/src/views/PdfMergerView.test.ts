import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PdfMergerView from './PdfMergerView.vue'
import { useFilesStore } from '../stores/pdfMerger/files'
import { usePlanStore } from '../stores/pdfMerger/plan'
import { listFiles, startMerge, watchJob } from '../api/PdfMergerClient'
import type { JobEvent } from '../api/pdfMergerTypes'
vi.mock('../api/PdfMergerClient')
vi.mock('vue-router', () => ({onBeforeRouteLeave: vi.fn()}))
const realShow = HTMLDialogElement.prototype.showModal
const realClose = HTMLDialogElement.prototype.close
beforeEach(() => {
  vi.clearAllMocks()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { HTMLDialogElement.prototype.showModal = realShow; HTMLDialogElement.prototype.close = realClose })
describe('PDF merger view', () => {
 it('preserves filename, source ranges, options and a running merge when changing mobile modes', async () => {
   vi.mocked(listFiles).mockResolvedValue([{ file_id: 'source', name: 'Report.pdf', kind: 'pdf', pages: 3, size: 1024, expires_at: 9999999999 }])
   vi.mocked(startMerge).mockResolvedValue({ job_id: 'job' })
   const stopWatcher = vi.fn()
   let onEvent: ((event: JobEvent) => void) | undefined
   vi.mocked(watchJob).mockImplementation((_id, callback) => { onEvent = callback; return stopWatcher })
   const pinia = createPinia()
   const wrapper = mount(PdfMergerView, { global: { plugins: [pinia], stubs: { PageThumb: true } } })
   await flushPromises()
   await wrapper.get('input[aria-label="Output file"]').setValue('My report.pdf')
   await wrapper.get('input[aria-label="Pages"]').setValue('1-2')
   const switchMode = async (prefix: string) => wrapper.findAll('.mobile-tabs button').find(b => b.text().startsWith(prefix))!.trigger('click')
   await switchMode('Files')
   expect(useFilesStore(pinia).sources[0]!.range).toBe('1-2')
   await wrapper.findAll('button').find(b => b.text().includes('Output options'))!.trigger('click')
   const options = wrapper.get('dialog[aria-label="Output options"]')
   await options.get('input[placeholder="Contract package"]').setValue('Report title')
   await options.get('button[aria-label="Close"]').trigger('click')
   await wrapper.get('button.primary').trigger('click')
   await flushPromises()
   expect(startMerge).toHaveBeenCalledWith(expect.objectContaining({ output: expect.objectContaining({ filename: 'My report.pdf', title: 'Report title' }) }))
   await switchMode('Pages')
   await switchMode('Files')
   expect(stopWatcher).not.toHaveBeenCalled()
   onEvent!({ type: 'progress', done: 1, total: 2 })
   await flushPromises()
   expect(wrapper.text()).toContain('Merging… 1 of 2 pages')
   expect((wrapper.get('input[aria-label="Output file"]').element as HTMLInputElement).value).toBe('My report.pdf')
   wrapper.unmount()
   expect(stopWatcher).toHaveBeenCalledOnce()
 })
 it('restores account files and stops polling when unmounted', async () => {
   vi.mocked(listFiles).mockResolvedValue([])
   const pinia = createPinia()
   const wrapper = mount(PdfMergerView,{global:{plugins:[pinia]}})
   const stopFiles = vi.spyOn(useFilesStore(pinia), 'stop')
   const stop = vi.spyOn(usePlanStore(pinia),'stop')
   await flushPromises()
   expect(listFiles).toHaveBeenCalled()
   expect(wrapper.text()).toContain('PDF merger')
   expect(wrapper.text()).toContain('15 MiB')
   wrapper.unmount()
   expect(stop).toHaveBeenCalled()
   expect(stopFiles).toHaveBeenCalled()
 })
})
