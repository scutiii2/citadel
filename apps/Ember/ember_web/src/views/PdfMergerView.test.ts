import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import PdfMergerView from './PdfMergerView.vue'
import { useFilesStore } from '../stores/pdfMerger/files'
import { usePlanStore } from '../stores/pdfMerger/plan'
import { listFiles } from '../api/PdfMergerClient'
vi.mock('../api/PdfMergerClient')
vi.mock('vue-router', () => ({onBeforeRouteLeave: vi.fn()}))
describe('PDF merger view', () => {
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
