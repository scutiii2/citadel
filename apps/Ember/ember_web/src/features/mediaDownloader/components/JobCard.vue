<script setup lang="ts">
import { computed } from 'vue'
import ActionButton from '../../../components/ui/buttons/ActionButton.vue'
import DownloadCards from '../../../components/content/DownloadCards.vue'
import ElapsedTime from '../../../components/ui/status/ElapsedTime.vue'
import { formatEta, formatSpeed } from '../utils/format'
import type { VideoJob } from '../stores/mediaDownloader'

const props = defineProps<{ job: VideoJob; busy?: boolean }>()
defineEmits<{ cancel: []; dismiss: [] }>()

const running = computed(() => ['queued', 'downloading', 'processing'].includes(props.job.state))
const stateText = computed(() => {
  switch (props.job.state) {
    case 'queued':
      return 'Waiting in line...'
    case 'processing':
      return 'Processing (merging and converting)...'
    case 'downloading':
      return `${Math.round(props.job.percent ?? 0)}%`
    case 'done':
      return 'Done'
    default:
      return ''
  }
})
</script>

<template>
  <li class="panel">
    <div class="row">
      <div class="grow">
        <div class="name">{{ job.title }} <span class="muted small">{{ job.presetLabel }}</span></div>
        <div role="status" v-if="job.state !== 'error'" class="muted small">
          ↓ {{ stateText }} <ElapsedTime v-if="running" :since="job.startedAt" />
          <template v-if="job.state === 'downloading'">
            <span v-if="job.speed !== null"> &middot; {{ formatSpeed(job.speed) }}</span>
            <span v-if="job.eta !== null"> &middot; {{ formatEta(job.eta) }} left</span>
          </template>
        </div>
        <div v-else class="error small" role="alert">{{ job.error?.message }}</div>
      </div>
      <ActionButton v-if="running && job.state !== 'processing'" icon="close" class="cancel danger" :disabled="busy" :aria-busy="busy" @click="$emit('cancel')">Cancel</ActionButton>

      <ActionButton v-if="!running" icon="close" quiet @click="$emit('dismiss')">Dismiss</ActionButton>
    </div>
    <DownloadCards v-if="job.state === 'done' && job.file" :downloads="[{ filename: job.file.name, bytes: job.file.size, href: job.file.download_url, label: 'DOWNLOAD' }]" />
    <p v-if="job.state === 'done' && !job.file" class="muted small">The download finished, but the file is no longer available.</p>
    <progress aria-label="Download progress" v-if="running" max="100" :value="job.state === 'processing' ? 100 : (job.percent ?? 0)"></progress>
  </li>
</template>

<style scoped src="./mediaDownloader.css"></style>
<style scoped>
.panel { padding: 16px; background: var(--bg); }
.row { align-items: flex-start; flex-wrap: nowrap; }
.grow { min-width: 0; }
.name { font-size: .9em; font-weight: 500; }
.name .small { display: block; margin-top: 3px; color: var(--muted); }
.grow > .small { margin-top: 6px; font-size: .75em; }
progress { height: 4px; border-radius: var(--radius-full); }
.panel :deep(button.action) { border-radius: var(--radius-full); }
.panel :deep(.action .label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
</style>
