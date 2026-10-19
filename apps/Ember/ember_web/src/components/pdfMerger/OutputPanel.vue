<script setup lang="ts">
import ToggleSwitch from '../ToggleSwitch.vue'
import SegmentedControl from '../SegmentedControl.vue'
// Output file name, metadata and image defaults.
import { usePlanStore } from '../../stores/pdfMerger/plan'

const plan = usePlanStore()
</script>

<template>
  <section class="panel">
    <h2>Output</h2>
    <div class="grid">
      <label>File name<input v-model="plan.output.filename" placeholder="merged.pdf" /></label>
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
/* Three-option pills are wider than a grid column; give them the whole row so they never scroll. */
.wide { grid-column: 1 / -1; }
</style>
