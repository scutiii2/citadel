<script setup lang="ts">
import ActionButton from "../ActionButton.vue"
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
    <ActionButton icon="verify" class="primary" type="submit" :aria-busy="loading" :disabled="!canCheck">{{ loading ? 'Checking...' : 'Check' }}</ActionButton>
  </form>
</template>

<style scoped src="./videoDownloader.css"></style>
