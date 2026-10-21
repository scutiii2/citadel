import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { videoDownloaderClient as api } from '../api/VideoDownloaderClient'
import type { MediaPackage } from '../api/VideoDownloaderTypes'
import { useAuthStore } from './auth'
import { videoError } from './videoDownloader'

export const useMediaPackagesStore = defineStore('mediaPackages', () => {
  const auth = useAuthStore()
  const packages = ref<MediaPackage[]>([])
  const error = ref<string | null>(null)
  const busy = ref(false)
  const loading = ref(false)
  let epoch = 0
  let request = 0
  let active = false
  let timer: ReturnType<typeof setTimeout> | undefined

  const editable = (id: string) => packages.value.some(p => p.package_id === id && p.state === 'draft' && !p.job_id)
  const removable = (id: string) => packages.value.some(p => p.package_id === id && ['draft', 'done', 'error'].includes(p.state))
  function replace(value: MediaPackage) {
    const index = packages.value.findIndex(p => p.package_id === value.package_id)
    if (index < 0) packages.value.push(value)
    else packages.value[index] = value
  }
  function schedule() {
    clearTimeout(timer)
    if (active && packages.value.some(p => p.job_id && !['done', 'error'].includes(p.state))) {
      timer = setTimeout(() => void refresh(), 2000)
    }
  }
  async function refresh(): Promise<void> {
    const generation = epoch
    const current = ++request
    loading.value = true
    try {
      const result = await api.listPackages()
      if (generation !== epoch || current !== request) return
      packages.value = result
    } catch (e) {
      if (generation === epoch && current === request) error.value = videoError(e)
    } finally {
      if (generation === epoch && current === request) { loading.value = false; schedule() }
    }
  }
  async function change(operation: (generation: number) => Promise<void>): Promise<boolean> {
    if (busy.value) return false
    const generation = epoch
    // Invalidate reads that could overwrite the accepted mutation with an old draft.
    request++
    loading.value = false
    clearTimeout(timer)
    busy.value = true
    error.value = null
    try {
      await operation(generation)
      return generation === epoch
    } catch (e) {
      if (generation === epoch) error.value = videoError(e)
      return false
    } finally {
      if (generation === epoch) { busy.value = false; schedule() }
    }
  }
  async function create(name: string) {
    return change(async generation => {
      const result = await api.createPackage(name.trim())
      if (generation === epoch) replace(result)
    })
  }
  async function add(id: string, text: string, preset: string): Promise<string[] | null> {
    if (!editable(id)) return null
    const urls = text.split(/\r?\n/).map(url => url.trim()).filter(Boolean)
    if (!urls.length || urls.length > 50) { error.value = 'Enter 1 to 50 URLs, one per line.'; return null }
    const failedUrls: string[] = []
    const ok = await change(async generation => {
      const failures: string[] = []
      for (const url of urls) {
        if (generation !== epoch) return
        try {
          const result = await api.addPackageItem(id, url, preset)
          if (generation === epoch) replace(result)
        } catch (e) { failedUrls.push(url); failures.push(`${url}: ${videoError(e)}`) }
      }
      if (generation === epoch && failures.length) error.value = failures.join('\n')
    })
    return ok ? failedUrls : null
  }
  async function remove(id: string, itemId: string) {
    if (!editable(id)) return false
    return change(async generation => {
      const result = await api.removePackageItem(id, itemId)
      if (generation === epoch) replace(result)
    })
  }
  async function start(id: string) {
    if (!editable(id)) return false
    return change(async generation => {
      const result = await api.startPackage(id)
      if (generation !== epoch) return
      const current = packages.value.find(p => p.package_id === id)
      if (current) { current.job_id = result.job_id; current.state = 'queued' }
    })
  }
  async function deletePackage(id: string) {
    if (!removable(id)) return false
    return change(async generation => {
      await api.deletePackage(id)
      if (generation === epoch) packages.value = packages.value.filter(p => p.package_id !== id)
    })
  }
  function stop() {
    active = false
    epoch++
    request++
    clearTimeout(timer)
    busy.value = loading.value = false
  }
  function activate() {
    if (active) return
    active = true
    void refresh()
  }
  watch(() => auth.account?.id, () => {
    const resume = active
    stop()
    packages.value = []
    error.value = null
    if (resume) activate()
  }, { flush: 'sync' })
  return { packages, error, busy, loading, editable, removable, create, add, remove, start, deletePackage, refresh, activate, stop }
})
