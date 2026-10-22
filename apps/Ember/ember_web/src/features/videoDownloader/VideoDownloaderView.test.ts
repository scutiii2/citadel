import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { videoDownloaderClient as api, watchVideoJob } from './api/VideoDownloaderClient'
import VideoDownloaderView from './VideoDownloaderView.vue'
import { useVideoDownloaderStore } from './stores/videoDownloader'
import { useAuthStore } from '../../stores/auth'

vi.mock('./api/VideoDownloaderClient', () => ({ videoDownloaderClient: { probe: vi.fn(), listFiles: vi.fn(), startDownload: vi.fn(), cancelJob: vi.fn(), deleteFile: vi.fn(), listPackages: vi.fn() }, watchVideoJob: vi.fn() }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
let wrapper: VueWrapper
const stop = vi.fn()
const realShow = HTMLDialogElement.prototype.showModal
const realClose = HTMLDialogElement.prototype.close
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.listPackages).mockResolvedValue([])
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  vi.mocked(api.listFiles).mockResolvedValue([{ file_id: 'f', name: 'Cat.mp4', kind: 'video', mime: 'video/mp4', size: 100, duration: 5, expires_at: Date.now() / 1000 + 3600, download_url: '/api/video-downloader/files/f/download' }])
  vi.mocked(api.probe).mockResolvedValue({ url: 'https://example.com/cat', title: 'Cat', duration: 5, thumbnail: 'http://unsafe/thumbnail', uploader: 'Uploader', options: [{ id: '720p', label: '720p', blocked: false, estimated_bytes: 100, code: null, reason: null, kind: 'video' }, { id: 'best', label: 'Best', blocked: true, estimated_bytes: 10000, code: 'too_large', reason: 'Too large', kind: 'video' }] })
  vi.mocked(api.startDownload).mockResolvedValue({ job_id: 'j' })
  vi.mocked(api.cancelJob).mockResolvedValue()
  vi.mocked(api.deleteFile).mockResolvedValue()
  vi.mocked(watchVideoJob).mockReturnValue(stop)
})
afterEach(() => { wrapper?.unmount(); HTMLDialogElement.prototype.showModal = realShow; HTMLDialogElement.prototype.close = realClose })
async function setup() { wrapper = mount(VideoDownloaderView, { attachTo: document.body, global: { plugins: [createPinia()] } }); await flushPromises() }
const button = (text: string) => (text === 'Download' ? wrapper.findAll('.probe button') : wrapper.findAll('button')).find(b => b.text() === text)!
async function start() {
  await wrapper.get('input[type=url]').setValue('https://example.com/cat')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  await button('Download').trigger('click')
  await flushPromises()
}
describe('VideoDownloaderView', () => {
  it('preserves a group draft and active watchers when switching workspace tabs', async () => {
    await setup()
    await start()
    await button('Download groups').trigger('click')
    const draft = wrapper.get<HTMLInputElement>('input[placeholder="My collection"]')
    await draft.setValue('Weekend collection')
    await button('Single link').trigger('click')
    await button('Download groups').trigger('click')
    expect(draft.element.value).toBe('Weekend collection')
    expect(stop).not.toHaveBeenCalled()
  })
  it('shows only the selected estimate while explaining unavailable formats', async () => {
    await setup()
    await wrapper.get('input[type=url]').setValue('https://example.com/cat')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.find('.selected-format').text()).toContain('720p')
    expect(wrapper.findAll('.blocked-presets li')).toHaveLength(1)
    expect(wrapper.find('.blocked-presets').text()).toContain('Too large')
  })
  it('downloads a TikTok photo carousel and explains the ZIP result', async () => {
    vi.mocked(api.probe).mockResolvedValue({ url: 'https://www.tiktok.com/@alice/photo/123', title: 'Holiday', duration: null, thumbnail: null, uploader: 'alice', photo_count: 3,
      options: [{ id: 'photos', label: 'Original photos', kind: 'photo', blocked: false, estimated_bytes: null, code: null, reason: null }] })
    await setup()
    expect(wrapper.text()).toContain('Media downloader')
    expect(wrapper.get('input[type=url]').attributes('aria-label')).toBe('Media link')
    await wrapper.get('input[type=url]').setValue('https://www.tiktok.com/@alice/photo/123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('3 photos')
    expect(wrapper.text()).toContain('ZIP')
    await button('Download').trigger('click')
    await flushPromises()
    expect(api.startDownload).toHaveBeenCalledWith('https://www.tiktok.com/@alice/photo/123', 'photos')
  })
  it('ports probe details, blocked presets, queued downloads and watcher cleanup', async () => {
    await setup()
    await wrapper.get('input[type=url]').setValue('https://example.com/cat')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Uploader')
    expect(wrapper.text()).toContain('Too large')
    expect(button('Best').attributes('disabled')).toBeDefined()
    expect(wrapper.find('img').exists()).toBe(false)
    await button('Download').trigger('click')
    await flushPromises()
    expect(api.startDownload).toHaveBeenCalledWith('https://example.com/cat', '720p')
    expect(wrapper.text()).toContain('Waiting in line')
    wrapper.unmount()
    expect(stop).toHaveBeenCalled()
  })
  it('deletes only after an Ember confirmation', async () => {
    await setup()
    await wrapper.get('button[aria-label="File options for Cat.mp4"]').trigger('click')
    await button('Delete file').trigger('click')
    expect(api.deleteFile).not.toHaveBeenCalled()
    document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
    await flushPromises()
    expect(api.deleteFile).toHaveBeenCalledWith('f')
    expect(wrapper.text()).toContain('Nothing here yet')
    expect(document.body.querySelector('dialog[open][aria-label="File details"]')).toBeNull()
  })
  it('disables saving expired files', async () => {
    await setup()
    const store = useVideoDownloaderStore()
    store.files[0]!.expires_at = 0
    await flushPromises()
    expect(wrapper.find('.save-file').exists()).toBe(false)
    expect(wrapper.text()).toContain('Expired')
  })
  it('offers file downloads only with files.download permission', async () => {
    await setup()
    const store = useVideoDownloaderStore()
    const permission = vi.spyOn(useAuthStore(), 'hasPermission').mockReturnValue(true)
    store.files = store.files.map(file => ({ ...file }))
    await flushPromises()
    expect(wrapper.get('.save-file').attributes('href')).toBe('/api/video-downloader/files/f/download')
    permission.mockReturnValue(false)
    store.files = store.files.map(file => ({ ...file }))
    await flushPromises()
    expect(wrapper.find('.save-file').exists()).toBe(false)
    expect(wrapper.text()).toContain('Download unavailable')
  })
  it('cancels only after confirmation', async () => {
    await setup()
    await start()
    await button('Cancel').trigger('click')
    expect(api.cancelJob).not.toHaveBeenCalled()
    document.body.querySelector<HTMLButtonElement>('dialog[open] .confirm')!.click()
    await flushPromises()
    expect(api.cancelJob).toHaveBeenCalledWith('j')
  })
})
