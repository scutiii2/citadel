<script setup lang="ts">
import { computed } from 'vue'
import ActionButton from '../../../components/ui/buttons/ActionButton.vue'
import CopyButton from '../../../components/ui/buttons/CopyButton.vue'
import SegmentedControl from '../../../components/ui/forms/SegmentedControl.vue'
import type { ProbeResult } from '../api/MediaDownloaderTypes'
import { formatBytes } from '../../../utils/format'
import { formatDuration } from '../utils/format'

const props = defineProps<{ result: ProbeResult; selected: string | null; busy?: boolean }>()
const emit = defineEmits<{ select: [id: string]; download: [] }>()
const choice = computed({ get: () => props.selected ?? '', set: id => emit('select', id) })
const options = computed(() => props.result.options.map(o => ({ value: o.id, label: o.label, disabled: o.blocked || props.busy })))
const selectedOption = computed(() => props.result.options.find(o => o.id === props.selected && !o.blocked))
const blockedOptions = computed(() => props.result.options.filter(o => o.blocked))

</script>

<template>
  <section class="panel probe" aria-label="Checked media">
    <div class="preview-row">
      <div class="preview muted small"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m10 9 5 3-5 3z" /></svg><span>Preview unavailable</span></div>
      <div class="preview-copy">
      <div class="title">{{ result.title }}</div>
      <div class="muted small">
        <span v-if="result.uploader">{{ result.uploader }}</span>
        <span v-if="result.uploader && result.duration !== null"> &middot; </span>
        <span v-if="result.duration !== null">{{ formatDuration(result.duration) }}</span>
      </div>
      <p v-if="result.photo_count" class="muted small">{{ result.photo_count }} {{ result.photo_count === 1 ? 'photo · Original image file' : 'photos · Downloaded together as a ZIP' }}</p>
      <CopyButton :text="result.url" label="Copy media link" />
      </div>
    </div>
    <div class="format-block">
      <div class="format-heading"><span>Download format</span><span class="muted">Available for this link</span></div>
      <SegmentedControl v-model="choice" :options="options" aria-label="Download quality" />
      <ul v-if="blockedOptions.length" class="blocked-presets">
        <li v-for="option in blockedOptions" :key="option.id" class="error small">{{ option.label }} — {{ option.reason ?? 'Unavailable' }}</li>
      </ul>
      <div class="download-line">
        <p class="selected-format muted small"><template v-if="selectedOption">{{ selectedOption.label }}<span v-if="selectedOption.estimated_bytes !== null"> · ~{{ formatBytes(selectedOption.estimated_bytes) }}</span></template><template v-else>Choose an available format.</template></p>
        <ActionButton icon="export" class="primary" :aria-busy="busy" :disabled="!selectedOption || busy" @click="$emit('download')">{{ busy ? 'Starting...' : 'Download' }}</ActionButton>
      </div>
    </div>
  </section>
</template>

<style scoped src="./mediaDownloader.css"></style>
<style scoped>
.panel.probe { display: block; padding: 0; overflow: hidden; background: var(--bg); }
.preview-row { display: flex; align-items: flex-start; gap: 16px; padding: 18px; }
.preview { width: 108px; height: 78px; aspect-ratio: auto; padding: 9px; flex-shrink: 0; gap: 5px; font-size: .6em; text-align: center; }
.preview svg { width: 24px; height: 24px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linejoin: round; }
.preview-copy { min-width: 0; }
.preview-copy .title { font-size: 1.1em; line-height: 1.5; }
.preview-copy .small { margin-top: 5px; font-size: .8em; }
.preview-copy :deep(button) { margin-top: 8px; }
.format-block { border-top: 1px solid var(--border); padding: 16px 18px 18px; }
.format-heading { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: .8em; }
.format-heading .muted { font-size: .9em; }
.probe :deep(.segmented) { padding: 0; border: 0; border-radius: 0; background: transparent; flex-wrap: wrap; overflow: visible; gap: 6px; }
.probe :deep(button.segment) { border: 1px solid var(--border); padding: 7px 12px; }
.probe :deep(button.segment.active) { border-color: var(--accent); }
.blocked-presets { margin: 12px 0 0; padding-left: 18px; }
.download-line { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 18px; }
.selected-format { margin: 0; }
.download-line :deep(button.action) { padding: 9px 16px; min-height: 40px; }
.download-line :deep(.action .label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
@media (max-width: 767px) {
  .preview-row { padding: 15px; gap: 12px; }
  .preview { width: 70px; height: 70px; font-size: .55em; }
  .preview-copy .title { font-size: .95em; }
  .format-block { padding: 14px 15px 16px; }
  .download-line { flex-direction: column; align-items: stretch; gap: 12px; margin-top: 14px; }
  .download-line :deep(button.action) { justify-content: center; min-height: 44px; }
}
</style>
