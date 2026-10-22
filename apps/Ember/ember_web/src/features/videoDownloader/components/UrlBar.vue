<script setup lang="ts">
import ActionButton from "../../../components/ui/buttons/ActionButton.vue"
defineProps<{ modelValue: string; loading: boolean; canCheck: boolean }>()
defineEmits<{ 'update:modelValue': [value: string]; check: [] }>()
</script>

<template>
  <form class="url-bar" @submit.prevent="$emit('check')">
    <input
      type="url"
      :value="modelValue"
      placeholder="Paste a video, music, photo or post link"
      aria-label="Media link"
      autofocus
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <ActionButton icon="verify" type="submit" :aria-busy="loading" :disabled="!canCheck">{{ loading ? 'Checking...' : 'Check' }}</ActionButton>
  </form>
</template>

<style scoped src="./videoDownloader.css"></style>
<style scoped>
.url-bar { flex-wrap: nowrap; gap: 8px; padding: 7px 8px 7px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.url-bar input { min-width: 0; padding: 4px 0; border: 0; border-radius: 0; background: transparent; font-size: .9em; }
.url-bar :deep(button.action) { border-radius: var(--radius-full); flex-shrink: 0; padding: 7px 12px; }
.url-bar :deep(.action .label) { position: static; width: auto; height: auto; overflow: visible; clip-path: none; }
@media (max-width: 767px) { .url-bar input { font-size: max(1em, 16px); } .url-bar :deep(button.action) { min-height: 40px; } }
</style>
