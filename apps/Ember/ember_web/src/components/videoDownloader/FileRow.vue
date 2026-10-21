<script setup lang="ts">
import ActionButton from "../ActionButton.vue"
import { useAuthStore } from '../../stores/auth'
import type { FileInfo } from '../../api/VideoDownloaderTypes'
import { formatBytes, formatDuration, formatExpiry } from '../../utils/videoDownloader/format'

defineProps<{ file: FileInfo; now: number; busy?: boolean }>()
defineEmits<{ details: [] }>()
const auth = useAuthStore()
</script>

<template>
  <li class="file-row">
    <div class="file-top">
      <span class="kind" :class="file.kind">{{ file.kind === 'package' ? 'ZIP' : file.mime === 'application/zip' ? 'ZIP' : file.kind === 'audio' ? 'music' : file.kind }}</span>
      <div class="file-copy">
        <div class="name" :title="file.name">{{ file.name }}</div>
        <div class="muted small">{{ formatBytes(file.size) }}<span v-if="file.duration !== null"> &middot; {{ formatDuration(file.duration) }}</span></div>
      </div>
    </div>
    <div class="file-actions">
      <span class="expiry muted">{{ file.expires_at > now ? `Expires in ${formatExpiry(file.expires_at, now)}` : 'Expired' }}</span>
      <a v-if="file.expires_at > now && auth.hasPermission('files.download')" class="save-file" :href="file.download_url" :aria-label="`Download ${file.name}`" download><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></svg>Save file</a>
      <span v-else class="unavailable muted">{{ file.expires_at > now ? 'Download unavailable' : 'Expired' }}</span>
      <ActionButton icon="more" icon-only :disabled="busy" :aria-busy="busy" :aria-label="`File options for ${file.name}`" :title="`File options for ${file.name}`" @click="$emit('details')">File options</ActionButton>
    </div>
  </li>
</template>

<style scoped src="./videoDownloader.css"></style>
<style scoped>
.file-row { padding: 18px 0; border-bottom: 1px solid var(--border); }
.file-top { display: flex; align-items: flex-start; gap: 10px; }
.file-copy { flex: 1; min-width: 0; }
.file-copy .name { font-size: .85em; font-weight: 500; }
.file-copy .small { margin-top: 5px; font-size: .75em; }
.kind { flex-shrink: 0; margin-top: 2px; font-size: .6em; }
.file-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.expiry { margin-right: auto; font-size: .7em; }
.save-file { display: inline-flex; align-items: center; gap: 5px; padding: 5px 10px; border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--bg); color: var(--text); font-size: .75em; text-decoration: none; }
.save-file svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.save-file:hover { border-color: var(--accent); }
.save-file:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.unavailable { font-size: .7em; }
button.action { border: 0; padding: 5px; }
@media (max-width: 767px) { .save-file, button.action { min-height: 40px; display: inline-flex; align-items: center; } .file-copy .name { font-size: .95em; } }
</style>
