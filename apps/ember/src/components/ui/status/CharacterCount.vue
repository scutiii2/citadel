<script setup lang="ts">
/** "12/200" under a text field. Give it the field's `aria-describedby` id as
 * `id`; `suffix` adds a unit, e.g. " characters". Alignment is the page's. */
defineProps<{ length: number; max: number; suffix?: string }>();
</script>

<template>
  <span class="character-count">{{ length }}/{{ max }}{{ suffix }}</span>
</template>

<style scoped>
.character-count { color: var(--muted); font-size: .8em; }
</style>
