<script setup lang="ts">
import WorkspaceLayout from "../../components/layout/WorkspaceLayout.vue";
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PageLayout from '../../components/layout/PageLayout.vue'
import ActionButton from '../../components/ui/buttons/ActionButton.vue'
import ConfirmModal from '../../components/ui/dialogs/ConfirmModal.vue'
import BaseModal from '../../components/ui/dialogs/BaseModal.vue'
import SegmentedControl from '../../components/ui/forms/SegmentedControl.vue'
import UrlBar from './components/UrlBar.vue'
import ProbeCard from './components/ProbeCard.vue'
import JobCard from './components/JobCard.vue'
import FileRow from './components/FileRow.vue'
import PackagePanel from './components/PackagePanel.vue'
import { useVideoDownloaderStore } from './stores/videoDownloader'
import { useAuthStore } from '../../stores/auth'
import { formatBytes, formatExpiry } from './utils/format'
import type { FileInfo } from './api/VideoDownloaderTypes'

const store = useVideoDownloaderStore()
const narrow = ref(window.matchMedia?.('(max-width: 767px)').matches ?? false)
const mediaQuery = window.matchMedia?.('(max-width: 767px)')
function updateViewport(event: MediaQueryListEvent): void { narrow.value = event.matches }
onMounted(() => mediaQuery?.addEventListener?.('change', updateViewport))
onBeforeUnmount(() => mediaQuery?.removeEventListener?.('change', updateViewport))
const auth = useAuthStore()
const now = ref(Date.now() / 1000)
const tab = ref<'download' | 'groups' | 'files'>('download')
const fileDetails = ref<FileInfo | null>(null)
const desktopTab = computed({ get: () => tab.value === 'files' ? 'download' : tab.value, set: (value: 'download' | 'groups') => { tab.value = value } })
const desktopTabs = [{ value: 'download' as const, label: 'Single link' }, { value: 'groups' as const, label: 'Download groups' }]
const mobileTabs = computed(() => [{ value: 'download' as const, label: 'Download' }, { value: 'groups' as const, label: 'Groups' }, { value: 'files' as const, label: `My files · ${store.files.length}` }])
const runningJobs = computed(() => store.jobs.filter(job => ['queued', 'downloading', 'processing'].includes(job.state)).length)
const confirm = ref<{ kind: 'cancel' | 'delete'; id: string; name: string } | null>(null)
const confirming = ref(false)
const confirmationMessage = computed(() => {
  const action = confirm.value
  if (!action) return ''
  const message = action.kind === 'delete' ? `Delete ${action.name}? This file will no longer be available.` : `Cancel ${action.name}?`
  const error = action.kind === 'delete' ? store.filesError : store.error
  return error ? `${message} ${error}` : message
})
let timer: ReturnType<typeof setInterval> | undefined
let generation = 0
function activate(): void {
  store.activate()
  if (timer === undefined) timer = setInterval(() => { now.value = Date.now() / 1000 }, 30_000)
}
function stop(): void {
  generation++
  store.stopWatching()
  clearInterval(timer)
  timer = undefined
  confirm.value = null
  fileDetails.value = null
  confirming.value = false
}
onMounted(activate)
onActivated(activate)
onDeactivated(stop)
onBeforeUnmount(stop)
onBeforeRouteLeave(stop)
watch(() => auth.account?.id, () => { generation++; confirm.value = null; confirming.value = false; fileDetails.value = null; tab.value = 'download' }, { flush: 'sync' })
async function confirmAction(): Promise<void> {
  const action = confirm.value
  if (!action || confirming.value) return
  const request = generation
  confirming.value = true
  const ok = action.kind === 'cancel' ? await store.cancel(action.id) : await store.remove(action.id)
  if (request !== generation) return
  confirming.value = false
  if (ok) {
    confirm.value = null
    if (action.kind === 'delete' && fileDetails.value?.file_id === action.id) fileDetails.value = null
  }
}
</script>

<template>
  <PageLayout class="media-page" title="Media downloader" description="Video, music, and photos. Start with a link." wide fill>
    <WorkspaceLayout mobile="stack" :class="['media-workspace', `mode-${tab}`]">
      <div class="mobile-tabs"><SegmentedControl mode="tabs" id-prefix="media-mobile" v-model="tab" :options="mobileTabs" aria-label="Media workspace" /></div>
      <div class="main-panel">
        <div class="desktop-tabs"><SegmentedControl mode="tabs" id-prefix="media-desktop" v-model="desktopTab" :options="desktopTabs" aria-label="Media workspace" /></div>
        <div v-show="tab !== 'groups'" :id="`media-${narrow ? 'mobile' : 'desktop'}-panel-download`" role="tabpanel" :aria-labelledby="`media-${narrow ? 'mobile' : 'desktop'}-tab-download`" class="download-panel">
          <h3 class="link-heading">Media link</h3>
          <UrlBar v-model="store.url" :loading="store.checking" :can-check="store.canCheck" @check="store.check()" />
          <p class="link-hint muted">Check a link to see the formats available for that media.</p>
          <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>
          <ProbeCard v-if="store.result" :result="store.result" :selected="store.selected" :busy="store.starting" @select="store.select" @download="store.start()" />
          <section v-if="store.jobs.length" class="jobs-panel" aria-label="Downloads">
            <div class="section-heading"><h3>Downloads</h3><span class="muted">{{ runningJobs }} active</span></div>
            <ul class="list">
              <JobCard v-for="job in store.jobs" :key="job.id" :job="job" :busy="store.cancelling.includes(job.id)" @cancel="confirm = { kind: 'cancel', id: job.id, name: job.title }" @dismiss="store.dismiss(job.id)" />
            </ul>
          </section>
          <p class="rights-note muted">Download only content you have the right to download.</p>
        </div>
        <div v-show="tab === 'groups'" :id="`media-${narrow ? 'mobile' : 'desktop'}-panel-groups`" role="tabpanel" :aria-labelledby="`media-${narrow ? 'mobile' : 'desktop'}-tab-groups`" class="groups-panel"><PackagePanel :source="store.result" :preset="store.selectedOption?.id ?? null" @completed="store.refreshFiles()" /></div>
      </div>
      <aside id="media-mobile-panel-files" :role="narrow ? 'tabpanel' : undefined" :aria-labelledby="narrow ? 'media-mobile-tab-files' : undefined" class="files-panel" aria-label="My files">
        <div class="files-heading"><h3>My files <span class="muted">{{ store.files.length }}</span></h3><ActionButton icon="summarize" :disabled="store.loadingFiles" :aria-busy="store.loadingFiles" @click="store.refreshFiles()">Refresh files</ActionButton></div>
        <p class="muted file-hint">Finished downloads are kept temporarily.</p>
        <p v-if="store.filesError" class="error" role="alert">{{ store.filesError }}</p>
        <p v-if="store.loadingFiles && !store.files.length" role="status">Loading files...</p>
        <p v-else-if="!store.files.length" class="muted empty-files">Nothing here yet. Finished downloads show up here until they expire.</p>
        <ul v-else class="file-list">
          <FileRow v-for="file in store.files" :key="file.file_id" :file="file" :now="now" :busy="store.removing.includes(file.file_id)" @details="fileDetails = file" />
        </ul>
        <p class="muted retention"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v6l4 2" /></svg>Save files to your device before they expire.</p>
      </aside>
    </WorkspaceLayout>
    <BaseModal :open="fileDetails !== null" title="File details" @close="!confirming && (fileDetails = null)">
      <div v-if="fileDetails" class="file-details">
        <p class="file-details-name">{{ fileDetails.name }}</p>
        <p class="muted">{{ formatBytes(fileDetails.size) }} · {{ fileDetails.expires_at > now ? `Expires in ${formatExpiry(fileDetails.expires_at, now)}` : 'Expired' }}</p>
        <div class="danger-zone"><span>Remove this file</span><ActionButton icon="clear" class="danger" :disabled="store.removing.includes(fileDetails.file_id)" @click="confirm = { kind: 'delete', id: fileDetails.file_id, name: fileDetails.name }">Delete file</ActionButton></div>
      </div>
    </BaseModal>
    <ConfirmModal :open="confirm !== null" :title="confirm?.kind === 'delete' ? 'Delete file?' : 'Cancel download?'" :message="confirmationMessage" :confirm-label="confirm?.kind === 'delete' ? 'Delete file' : 'Cancel download'" danger :busy="confirming" @confirm="confirmAction" @close="!confirming && (confirm = null)" />
  </PageLayout>
</template>

<style scoped>
.media-workspace { --workspace-columns: minmax(0, 1fr) 300px; }
.main-panel { padding: 22px 24px; min-width: 0; min-height: 0; overflow-y: auto; }
.desktop-tabs { margin-bottom: 22px; }
.mobile-tabs { display: none; }
.download-panel { min-width: 0; }
.link-heading { margin-bottom: 10px; font-size: .85em; }
.link-hint { margin: 8px 0 20px; font-size: .75em; }
.jobs-panel { margin-top: 24px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-heading span { font-size: .75em; }
.section-heading h3 { margin: 0; }
.list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.file-list { list-style: none; margin: 0; padding: 0; }
.files-panel { border-left: 1px solid var(--border); background: color-mix(in srgb, var(--surface) 45%, var(--bg)); padding: 22px 18px; min-width: 0; min-height: 0; overflow-y: auto; }
.files-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.files-heading h3 { margin: 0; }
.files-heading h3 span { font-size: .8em; font-weight: 400; }
.file-hint { margin: 10px 0 4px; font-size: .75em; }
.empty-files { padding: 16px 0; }
.files-panel :deep(button.action) { border-radius: var(--radius-full); }
.files-heading :deep(.action .label) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.retention { display: flex; align-items: flex-start; gap: 8px; margin-top: 20px; font-size: .75em; }
.retention svg { width: 15px; height: 15px; margin-top: 2px; flex-shrink: 0; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.rights-note { margin: 24px 0 0; font-size: .75em; }
.file-details { overflow-wrap: anywhere; }
.file-details-name { font-weight: 600; }
.danger-zone { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 24px; padding: 12px; border: 1px solid var(--danger); border-radius: var(--radius-lg); font-size: .85em; }
.danger-zone :deep(button.action) { color: var(--danger); border-color: var(--danger); border-radius: var(--radius-full); }
.danger-zone :deep(.action .label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
.danger-zone :deep(.action .icon) { stroke: currentColor; }
h3 { font-size: 1em; margin: 0 0 12px; }
.error { color: var(--danger); overflow-wrap: anywhere; }
.muted { color: var(--muted); font-size: .85em; }
@media (max-width: 1050px) and (min-width: 768px) { .media-workspace { --workspace-columns: minmax(0, 1fr) 250px; } .main-panel { padding: 20px 18px; } .files-panel { padding-inline: 14px; } }
@media (max-width: 767px) {
  .media-page :deep(.page-column) { padding: 20px 16px 12px; }
  .media-page :deep(.page-head) { margin-bottom: 18px; }
  .mobile-tabs { display: block; flex-shrink: 0; margin-bottom: 18px; }
  .mobile-tabs :deep(.segmented-control), .mobile-tabs :deep(.segmented) { width: 100%; }
  .mobile-tabs :deep(button.segment) { flex: 1; min-height: 44px; padding-inline: 7px; }
  .desktop-tabs { display: none; }
  .main-panel { flex: 1; padding: 0 0 16px; }
  .files-panel { flex: 1; border: 0; padding: 0 0 16px; background: var(--bg); }
  .media-workspace:not(.mode-files) .files-panel, .mode-files .main-panel { display: none; }
}
</style>
