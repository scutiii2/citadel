import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import PackagePanel from './PackagePanel.vue'
import { videoDownloaderClient as api } from '../../api/VideoDownloaderClient'
import type { MediaPackage } from '../../api/VideoDownloaderTypes'

vi.mock('../../api/VideoDownloaderClient', () => ({ videoDownloaderClient: {
  listPackages: vi.fn(), createPackage: vi.fn(), addPackageItem: vi.fn(), removePackageItem: vi.fn(), startPackage: vi.fn(),
} }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
let wrapper: VueWrapper
const realShow = HTMLDialogElement.prototype.showModal
const realClose = HTMLDialogElement.prototype.close
beforeEach(() => {
  vi.resetAllMocks()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  vi.mocked(api.listPackages).mockResolvedValue([])
})
afterEach(() => { wrapper?.unmount(); HTMLDialogElement.prototype.showModal = realShow; HTMLDialogElement.prototype.close = realClose })

it('builds a group, confirms starting and hides every membership editor after acceptance', async () => {
  const draft: MediaPackage = { package_id: 'p', name: 'Collection', state: 'draft', items: [], status: null, job_id: null }
  vi.mocked(api.createPackage).mockResolvedValue(draft)
  vi.mocked(api.addPackageItem).mockResolvedValue({ ...draft, items: [{ item_id: 'i', url: 'https://example.com/a', preset: 'best', title: null, state: 'pending', error: null }] })
  vi.mocked(api.startPackage).mockResolvedValue({ job_id: 'j' })
  wrapper = mount(PackagePanel, { props: { source: null, preset: null }, attachTo: document.body, global: { plugins: [createPinia()] } })
  await flushPromises()
  await wrapper.get('input').setValue('Collection')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('✎ Draft')
  await wrapper.get('textarea').setValue('https://example.com/a')
  await wrapper.findAll('button').find(b => b.text() === 'Add links')!.trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('https://example.com/a')
  await wrapper.findAll('button').find(b => b.text() === 'Download package')!.trigger('click')
  await flushPromises()
  expect(wrapper.find('textarea').exists()).toBe(true)
  expect(document.body.querySelector('dialog[open]')?.textContent).toContain('permanently locked')
  document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
  await flushPromises()
  expect(wrapper.text()).toContain('🔒 Locked')
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.findAll('button').some(b => b.text() === 'Remove')).toBe(false)
  expect(wrapper.find('progress').exists()).toBe(true)
})
