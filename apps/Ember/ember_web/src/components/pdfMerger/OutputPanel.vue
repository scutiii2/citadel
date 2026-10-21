<script setup lang="ts">
import ToggleSwitch from '../ToggleSwitch.vue'
import SegmentedControl from '../SegmentedControl.vue'
// Output file name, metadata and image defaults.
import { usePlanStore } from '../../stores/pdfMerger/plan'

const plan = usePlanStore()
</script>

<template>
  <section class="output-options" aria-label="PDF output settings">
    <div class="grid">
      <label>Title<input v-model="plan.output.title" placeholder="Contract package" /></label>
      <label>Author<input v-model="plan.output.author" placeholder="Jane Cruz" /></label>
      <SegmentedControl class="wide" v-model="plan.output.image_page_size" label="Image page size" :options="[{value:'A4',label:'A4'},{value:'Letter',label:'Letter'},{value:'match',label:'Match image'}]" />
      <SegmentedControl class="wide" v-model="plan.output.image_fit" label="Image fit" :options="[{value:'fit',label:'Fit page'},{value:'fill',label:'Fill page'},{value:'original',label:'Original size'}]" />
      <label
        >Image margin (mm)
        <input v-model.number="plan.output.image_margin_mm" type="number" min="0" max="50" step="1" />
      </label>
      <ToggleSwitch :checked="plan.output.bookmarks" @change="plan.output.bookmarks = ($event.target as HTMLInputElement).checked">Bookmark each source</ToggleSwitch>
    </div>
  </section>
</template>
<style scoped>
.grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
.grid > label:not(.toggle) { display: grid; gap: 6px; font-size: .85em; color: var(--muted); }
input { font: inherit; width: 100%; min-width: 0; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 9px 11px; }
input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
/* Three-option pills are wider than a grid column; give them the whole row so they never scroll. */
.wide { grid-column: 1 / -1; }
</style>
