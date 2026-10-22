import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import PackagePanel from './PackagePanel.vue'
import { videoDownloaderClient as api } from '../api/VideoDownloaderClient'
import type { MediaPackage } from '../api/VideoDownloaderTypes'
import { ApiError } from '../../../api/http'

vi.mock('../api/VideoDownloaderClient', () => ({ videoDownloaderClient: {
  listPackages: vi.fn(), createPackage: vi.fn(), addPackageItem: vi.fn(), removePackageItem: vi.fn(), startPackage: vi.fn(), deletePackage: vi.fn(),
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

it('confirms package removal, displays a refusal, and removes the group after retry', async () => {
  vi.mocked(api.listPackages).mockResolvedValue([{ package_id: 'p', name: 'Collection', state: 'draft', job_id: null, status: null, items: [] }])
  vi.mocked(api.deletePackage).mockRejectedValueOnce(new Error('Still downloading')).mockResolvedValueOnce(undefined)
  wrapper = mount(PackagePanel, { props: { source: null, preset: null }, attachTo: document.body, global: { plugins: [createPinia()] } })
  await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === 'Remove package')!.trigger('click')
  expect(api.deletePackage).not.toHaveBeenCalled()
  expect(document.body.querySelector('dialog[open]')?.textContent).toContain('Downloaded files will remain')
  document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
  await flushPromises()
  expect(document.body.querySelector('dialog[open]')?.textContent).toContain('Still downloading')
  expect(wrapper.find('article').exists()).toBe(true)
  document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
  await flushPromises()
  expect(wrapper.find('article').exists()).toBe(false)
})

it('shows a refused start inside the confirmation and allows retry without locking the draft', async () => {
  const message = "FFmpeg is missing. Install FFmpeg on armory's PATH, then try again."
  vi.mocked(api.listPackages).mockResolvedValue([{ package_id: 'p', name: 'Collection', state: 'draft', job_id: null, status: null,
    items: [{ item_id: 'i', url: 'https://example.com/a', preset: 'best', title: null, state: 'pending', error: null }] }])
  vi.mocked(api.startPackage).mockRejectedValueOnce(new ApiError(503, message, 'ffmpeg_missing')).mockResolvedValueOnce({ job_id: 'j' })
  wrapper = mount(PackagePanel, { props: { source: null, preset: null }, attachTo: document.body, global: { plugins: [createPinia()] } })
  await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === 'Download package')!.trigger('click')
  document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
  await flushPromises()
  expect(document.body.querySelector('dialog[open]')?.textContent).toContain(message)
  expect(document.body.querySelector('dialog[open]')?.textContent).toContain('permanently locked')
  expect(wrapper.text()).toContain('✎ Draft')
  expect(wrapper.find('textarea').exists()).toBe(true)
  document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
  await flushPromises()
  expect(document.body.querySelector('dialog[open]')).toBeNull()
  expect(wrapper.text()).toContain('🔒 Locked')
  expect(api.startPackage).toHaveBeenCalledTimes(2)
})

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
