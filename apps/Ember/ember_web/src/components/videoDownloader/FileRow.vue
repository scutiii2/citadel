<script setup lang="ts">
import ActionButton from "../ActionButton.vue"
import DownloadCards from "../DownloadCards.vue"
import type { FileInfo } from '../../api/VideoDownloaderTypes'
import { formatBytes, formatDuration, formatExpiry } from '../../utils/videoDownloader/format'

defineProps<{ file: FileInfo; now: number; busy?: boolean }>()
defineEmits<{ remove: [] }>()
</script>

<template>
  <li class="row">
    <span class="kind" :class="file.kind">{{ file.mime === 'application/zip' ? 'photo ZIP' : file.kind === 'audio' ? 'music' : file.kind }}</span>
    <div class="grow">
      <div class="name" :title="file.name">{{ file.name }}</div>
      <div class="muted small">
        {{ formatBytes(file.size) }}
        <span v-if="file.duration !== null"> &middot; {{ formatDuration(file.duration) }}</span>
        &middot; expires in {{ formatExpiry(file.expires_at, now) }}
      </div>
    </div>
    <DownloadCards :downloads="[{ filename: file.name, bytes: file.size, href: file.expires_at > now ? file.download_url : null, label: file.mime === 'application/zip' ? 'ZIP' : file.kind === 'audio' ? 'MUSIC' : file.kind.toUpperCase() }]" />
    <ActionButton icon="clear" class="danger" :disabled="busy" :aria-busy="busy" @click="$emit('remove')">Delete</ActionButton>
  </li>
</template>

<style scoped src="./videoDownloader.css"></style>
