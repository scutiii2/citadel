<script setup lang="ts">
import { computed } from 'vue'
import ActionButton from '../ActionButton.vue'
import CopyButton from '../CopyButton.vue'
import SegmentedControl from '../SegmentedControl.vue'
import type { ProbeResult } from '../../api/VideoDownloaderTypes'
import { formatBytes, formatDuration } from '../../utils/videoDownloader/format'

const props = defineProps<{ result: ProbeResult; selected: string | null; busy?: boolean }>()
const emit = defineEmits<{ select: [id: string]; download: [] }>()
const choice = computed({ get: () => props.selected ?? '', set: id => emit('select', id) })
const options = computed(() => props.result.options.map(o => ({ value: o.id, label: o.label, disabled: o.blocked })))

</script>

<template>
  <section class="panel probe">
    <div class="preview muted small">Preview unavailable</div>
    <div>
      <div class="title">{{ result.title }}</div>
      <div class="muted small">
        <span v-if="result.uploader">{{ result.uploader }}</span>
        <span v-if="result.uploader && result.duration !== null"> &middot; </span>
        <span v-if="result.duration !== null">{{ formatDuration(result.duration) }}</span>
      </div>
      <p v-if="result.photo_count" class="muted small">{{ result.photo_count }} {{ result.photo_count === 1 ? 'photo · Original image file' : 'photos · Downloaded together as a ZIP' }}</p>
      <CopyButton :text="result.url" label="Copy media link" />
      <SegmentedControl v-model="choice" :options="options" aria-label="Download quality" />
      <ul class="presets">
        <li v-for="option in result.options" :key="option.id">
          <span>{{ option.label }}</span>
          <span v-if="option.estimated_bytes !== null" class="muted small"> ~{{ formatBytes(option.estimated_bytes) }}</span>
          <span v-if="option.blocked" class="error small"> — {{ option.reason ?? 'Unavailable' }}</span>
        </li>
      </ul>
      <ActionButton icon="export" class="primary" :aria-busy="busy" :disabled="selected === null || busy" @click="$emit('download')">{{ busy ? 'Starting...' : 'Download' }}</ActionButton>
    </div>
  </section>
</template>

<style scoped src="./videoDownloader.css"></style>
