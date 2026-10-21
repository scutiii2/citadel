<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PageLayout from '../components/PageLayout.vue'
import ActionButton from '../components/ActionButton.vue'
import ConfirmModal from '../components/ConfirmModal.vue'
import UrlBar from '../components/videoDownloader/UrlBar.vue'
import ProbeCard from '../components/videoDownloader/ProbeCard.vue'
import JobCard from '../components/videoDownloader/JobCard.vue'
import FileRow from '../components/videoDownloader/FileRow.vue'
import PackagePanel from '../components/videoDownloader/PackagePanel.vue'
import { useVideoDownloaderStore } from '../stores/videoDownloader'
import { useAuthStore } from '../stores/auth'
import { plural } from '../utils/videoDownloader/format'

const store = useVideoDownloaderStore()
const auth = useAuthStore()
const now = ref(Date.now() / 1000)
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
  confirming.value = false
}
onMounted(activate)
onActivated(activate)
onDeactivated(stop)
onBeforeUnmount(stop)
onBeforeRouteLeave(stop)
watch(() => auth.account?.id, () => { generation++; confirm.value = null; confirming.value = false }, { flush: 'sync' })
async function confirmAction(): Promise<void> {
  const action = confirm.value
  if (!action || confirming.value) return
  const request = generation
  confirming.value = true
  const ok = action.kind === 'cancel' ? await store.cancel(action.id) : await store.remove(action.id)
  if (request !== generation) return
  confirming.value = false
  if (ok) confirm.value = null
}
</script>

<template>
  <PageLayout title="Media downloader" :description="`Video, music and photos · ${plural(store.files.length, 'file')} kept for a few hours`">
    <div class="video-downloader">
      <UrlBar v-model="store.url" :loading="store.checking" :can-check="store.canCheck" @check="store.check()" />
      <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>
      <ProbeCard v-if="store.result" :result="store.result" :selected="store.selected" :busy="store.starting" @select="store.select" @download="store.start()" />
      <PackagePanel :source="store.result" :preset="store.selectedOption?.id ?? null" @completed="store.refreshFiles()" />
      <section v-if="store.jobs.length" aria-label="Downloads">
        <h3>Downloads</h3>
        <ul class="list">
          <JobCard v-for="job in store.jobs" :key="job.id" :job="job" :busy="store.cancelling.includes(job.id)" @cancel="confirm = { kind: 'cancel', id: job.id, name: job.title }" @dismiss="store.dismiss(job.id)" />
        </ul>
      </section>
      <section class="files-panel" aria-label="My files">
        <div class="files-heading"><h3>My files</h3><ActionButton icon="summarize" :disabled="store.loadingFiles" :aria-busy="store.loadingFiles" @click="store.refreshFiles()">Refresh files</ActionButton></div>
        <p v-if="store.filesError" class="error" role="alert">{{ store.filesError }}</p>
        <p v-if="store.loadingFiles && !store.files.length" role="status">Loading files...</p>
        <p v-else-if="!store.files.length" class="muted">Nothing here yet. Finished downloads show up here until they expire.</p>
        <ul v-else class="list">
          <FileRow v-for="file in store.files" :key="file.file_id" :file="file" :now="now" :busy="store.removing.includes(file.file_id)" @remove="confirm = { kind: 'delete', id: file.file_id, name: file.name }" />
        </ul>
      </section>
      <p class="muted">Download only content you have the right to download.</p>
    </div>
    <ConfirmModal :open="confirm !== null" :title="confirm?.kind === 'delete' ? 'Delete file?' : 'Cancel download?'" :message="confirmationMessage" :confirm-label="confirm?.kind === 'delete' ? 'Delete file' : 'Cancel download'" danger :busy="confirming" @confirm="confirmAction" @close="!confirming && (confirm = null)" />
  </PageLayout>
</template>

<style scoped>
.video-downloader { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.files-panel { border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); padding: 14px; min-width: 0; }
.files-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h3 { font-size: 1em; margin: 0 0 12px; }
.error { color: var(--danger); overflow-wrap: anywhere; }
.muted { color: var(--muted); font-size: .85em; }
</style>
