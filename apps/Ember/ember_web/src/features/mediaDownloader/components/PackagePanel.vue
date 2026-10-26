<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import ActionButton from '../../../components/ui/buttons/ActionButton.vue'
import ConfirmModal from '../../../components/ui/dialogs/ConfirmModal.vue'
import DownloadCards from '../../../components/content/DownloadCards.vue'
import type { ProbeResult } from '../api/MediaDownloaderTypes'
import { useMediaPackagesStore } from '../stores/mediaPackages'
import { useAuthStore } from '../../../stores/auth'

defineProps<{ source: ProbeResult | null; preset: string | null }>()
const emit = defineEmits<{ completed: [] }>()
const store = useMediaPackagesStore()
const auth = useAuthStore()
const name = ref('')
const drafts = reactive<Record<string, string>>({})
const presets = reactive<Record<string, string>>({})
const confirm = ref<{ kind: 'start' | 'remove' | 'delete-package'; id: string; itemId?: string; name: string; error?: string } | null>(null)
const confirmTitle = computed(() => confirm.value?.kind === 'start' ? 'Start package download?' : confirm.value?.kind === 'delete-package' ? 'Remove this package?' : 'Remove media?')
const confirmLabel = computed(() => confirm.value?.kind === 'start' ? 'Start download' : confirm.value?.kind === 'delete-package' ? 'Remove package' : 'Remove media')
const confirmMessage = computed(() => {
  const action = confirm.value
  if (!action) return ''
  const message = action.kind === 'start' ? `Start ${action.name}? Its media list will be permanently locked.`
    : action.kind === 'delete-package' ? `Remove ${action.name} and its media list? Downloaded files will remain available separately.`
    : `Remove ${action.name} from this group?`
  return message + (action.error ? ` ${action.error}` : '')
})
const choices = [ ['best', 'Best video'], ['1080p', '1080p'], ['720p', '720p'], ['480p', '480p'], ['audio-mp3', 'MP3 music'], ['audio-m4a', 'M4A music'], ['photos', 'Original photos'] ]
onMounted(store.activate)
onActivated(store.activate)
onDeactivated(store.stop)
onBeforeUnmount(store.stop)
onBeforeRouteLeave(store.stop)
watch(() => auth.account?.id, () => {
  name.value = ''
  confirm.value = null
  Object.keys(drafts).forEach(key => delete drafts[key])
  Object.keys(presets).forEach(key => delete presets[key])
}, { flush: 'sync' })
watch(() => store.packages.filter(p => p.state === 'done').map(p => p.package_id).join(','), (value, old) => {
  if (value && value !== old) emit('completed')
})
async function create() { if (await store.create(name.value)) name.value = '' }
async function add(id: string) {
  const failed = await store.add(id, drafts[id] ?? '', presets[id] ?? 'best')
  if (failed) drafts[id] = failed.join('\n')
}
async function confirmAction() {
  const action = confirm.value
  if (!action) return
  const ok = action.kind === 'start' ? await store.start(action.id) : action.kind === 'delete-package' ? await store.deletePackage(action.id) : await store.remove(action.id, action.itemId!)
  if (ok) {
    if (action.kind === 'delete-package') { delete drafts[action.id]; delete presets[action.id] }
    confirm.value = null
  }
  else if (confirm.value === action) confirm.value = { ...action, error: store.error ?? 'The operation could not be completed. Try again.' }
}
</script>

<template>
  <section class="packages" aria-label="Download groups">
    <div class="heading"><h3>Download groups</h3><ActionButton icon="summarize" :disabled="store.loading || store.busy" :aria-busy="store.loading" @click="store.refresh()">Refresh groups</ActionButton></div>
    <p class="muted">Build a group, then download it as one ZIP. Starting locks its media list.</p>
    <form class="create-group" @submit.prevent="create">
      <label class="grow">Group name<input v-model="name" maxlength="150" placeholder="My collection" :disabled="store.busy" /></label>
      <ActionButton icon="verify" type="submit" :disabled="!name.trim() || store.busy" :aria-busy="store.busy">Create group</ActionButton>
    </form>
    <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>
    <p v-if="!store.packages.length" class="muted">Create a group to collect multiple media links.</p>
    <article v-for="group in store.packages" :key="group.package_id" class="group" :aria-label="group.name">
      <div class="heading"><h4>{{ group.name }}</h4><span class="state">{{ group.state === 'draft' ? '✎ Draft' : '🔒 Locked' }} · {{ group.state }}</span></div>
      <ul class="items">
        <li v-for="item in group.items" :key="item.item_id">
          <div class="grow"><span>{{ item.title || item.url }}</span><small class="muted">{{ item.preset }} · {{ item.state }}</small><small v-if="item.error" class="error">{{ item.error.message }}</small></div>
          <ActionButton v-if="store.editable(group.package_id)" icon="clear" class="danger" :disabled="store.busy" @click="confirm = { kind: 'remove', id: group.package_id, itemId: item.item_id, name: item.title || item.url }">Remove</ActionButton>
        </li>
      </ul>
      <div v-if="store.editable(group.package_id)" class="editor">
        <ActionButton v-if="source && preset" icon="verify" :disabled="store.busy" :aria-busy="store.busy" @click="store.add(group.package_id, source.url, preset)">Add checked media</ActionButton>
        <label>Media links, one per line<textarea v-model="drafts[group.package_id]" rows="3" placeholder="https://…" :disabled="store.busy" /></label>
        <label>Download format<select v-model="presets[group.package_id]" :disabled="store.busy"><option :value="undefined" disabled>Best video (default)</option><option v-for="choice in choices" :key="choice[0]" :value="choice[0]">{{ choice[1] }}</option></select></label>
        <div class="actions">
          <ActionButton icon="verify" :disabled="!drafts[group.package_id]?.trim() || store.busy" :aria-busy="store.busy" @click="add(group.package_id)">Add links</ActionButton>
          <ActionButton icon="export" class="primary" :disabled="!group.items.length || store.busy" :aria-busy="store.busy" @click="confirm = { kind: 'start', id: group.package_id, name: group.name }">Download package</ActionButton>
        </div>
      </div>
      <div v-else class="result">
        <p class="muted">This package is locked. Create a new group to add more media.</p>
        <progress v-if="!['done', 'error'].includes(group.state)" :value="group.status?.percent ?? undefined" max="100" :aria-label="`${group.name} download progress`" />
        <p v-if="group.status?.error" class="error" role="alert">{{ group.status.error.message }}</p>
        <p v-if="group.state === 'done' && group.items.some(item => item.state === 'error')" class="muted">ZIP ready with the successful files. Failed links are shown above.</p>
        <DownloadCards v-if="group.status?.file" :downloads="[{ filename: group.status.file.name, bytes: group.status.file.size, href: group.status.file.download_url, label: 'ZIP' }]" />
      </div>
      <div class="danger-zone">
        <span>{{ store.removable(group.package_id) ? 'Remove this group and its media list.' : 'Wait for the download to finish before removing this package.' }}</span>
        <ActionButton icon="clear" class="danger" :disabled="store.busy || !store.removable(group.package_id)" @click="confirm = { kind: 'delete-package', id: group.package_id, name: group.name }">Remove package</ActionButton>
      </div>
    </article>
    <Teleport to="body"><ConfirmModal v-if="confirm" :open="true" :title="confirmTitle" :message="confirmMessage" :confirm-label="confirmLabel" :danger="confirm.kind !== 'start'" :busy="store.busy" @confirm="confirmAction" @close="!store.busy && (confirm = null)" /></Teleport>
  </section>
</template>

<style scoped src="./mediaDownloader.css"></style>
<style scoped>
.packages, .group { border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); padding: 14px; min-width: 0; }
.packages, .editor { display: flex; flex-direction: column; gap: 12px; }
.heading, .create-group, .actions, .items li { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.heading { justify-content: space-between; }
.create-group { align-items: end; }
.grow { flex: 1; min-width: 0; overflow-wrap: anywhere; }
h3, h4, p { margin: 0; }
h3, h4 { font-size: 1em; }
label { display: flex; flex-direction: column; gap: 5px; font-size: .9em; }
input, textarea, select { box-sizing: border-box; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
textarea { resize: vertical; }
input:focus-visible, textarea:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.items { list-style: none; margin: 10px 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
small { display: block; }
.muted, .state { color: var(--muted); font-size: .85em; }
.error { color: var(--danger); white-space: pre-line; overflow-wrap: anywhere; }
.result { display: flex; flex-direction: column; gap: 10px; }
.danger-zone { margin-top: 14px; }
.packages :deep(button.action) { border-radius: var(--radius-full); }
.packages :deep(button.action .label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
.packages { padding: 0; border: 0; border-radius: 0; background: transparent; }
.group { background: var(--bg); padding: 18px; }
.items li { padding: 12px 0; border-bottom: 1px solid var(--border); }
.items li .grow { min-width: 0; }
progress { width: 100%; accent-color: var(--accent); }
@media (max-width: 767px) { .create-group { align-items: stretch; flex-direction: column; } }
</style>
