import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { videoDownloaderClient as api } from '../api/VideoDownloaderClient'
import { useMediaPackagesStore } from './mediaPackages'
import { useAuthStore } from './auth'
import type { MediaPackage } from '../api/VideoDownloaderTypes'

vi.mock('../api/VideoDownloaderClient', () => ({ videoDownloaderClient: {
  listPackages: vi.fn(), createPackage: vi.fn(), addPackageItem: vi.fn(), startPackage: vi.fn(), removePackageItem: vi.fn(),
} }))
const draft: MediaPackage = { package_id: 'p', name: 'Mix', state: 'draft', items: [], job_id: null, status: null }

beforeEach(() => { vi.resetAllMocks(); setActivePinia(createPinia()); vi.mocked(api.listPackages).mockResolvedValue([structuredClone(draft)]) })

describe('media packages', () => {
  it('locks the group as soon as starting is accepted', async () => {
    const store = useMediaPackagesStore()
    await store.refresh()
    vi.mocked(api.startPackage).mockResolvedValue({ job_id: 'j' })
    await store.start('p')
    expect(store.packages[0]?.job_id).toBe('j')
    expect(store.packages[0]?.state).toBe('queued')
    expect(store.editable('p')).toBe(false)
  })
  it('keeps a rejected start editable and reports the failure', async () => {
    const store = useMediaPackagesStore()
    await store.refresh()
    vi.mocked(api.startPackage).mockRejectedValue(new Error('Queue full'))
    await store.start('p')
    expect(store.editable('p')).toBe(true)
    expect(store.error).toContain('Queue full')
  })
  it('reports failed links while retaining successful additions', async () => {
    const store = useMediaPackagesStore()
    await store.refresh()
    vi.mocked(api.addPackageItem).mockRejectedValueOnce(new Error('Blocked URL')).mockResolvedValueOnce({ ...draft,
      items: [{ item_id: 'i', url: 'https://example.com/good', preset: 'best', title: null, state: 'pending', error: null }] })
    const failed = await store.add('p', 'https://example.com/bad\nhttps://example.com/good', 'best')
    expect(store.packages[0]?.items).toHaveLength(1)
    expect(store.error).toContain('Blocked URL')
    expect(failed).toEqual(['https://example.com/bad'])
  })
  it('discards a late response after account change', async () => {
    const store = useMediaPackagesStore()
    let resolve!: (value: typeof draft[]) => void
    vi.mocked(api.listPackages).mockReturnValue(new Promise(r => { resolve = r }))
    const loading = store.refresh()
    useAuthStore().$patch({ account: { id: 2 } as never })
    resolve([draft])
    await loading
    expect(store.packages).toEqual([])
    expect(store.loading).toBe(false)
  })
})
