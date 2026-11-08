<script setup lang="ts">
/** The loading, load-error and empty notices of a list page. `loading` is a
 * status line; `error` is an alert with a "Try again" button (the page handles
 * `@retry`); `empty` has an optional `title`, the text, and an `action` slot
 * for a button. The text goes in the default slot. */
defineProps<{ kind: "loading" | "error" | "empty"; title?: string }>();
defineEmits<{ retry: [] }>();
</script>

<template>
  <p v-if="kind === 'loading'" class="state" role="status"><slot /></p>
  <div v-else-if="kind === 'error'" class="state error" role="alert">
    <p><slot /></p>
    <button type="button" class="chip" @click="$emit('retry')">Try again</button>
  </div>
  <div v-else class="state">
    <h3 v-if="title">{{ title }}</h3>
    <p><slot /></p>
    <slot name="action" />
  </div>
</template>

<style scoped>
.state { padding: 20px 10px; font-size: .85em; color: var(--muted); overflow-wrap: anywhere; }
.state.error { color: var(--danger); }
.state h3 { margin: 0 0 8px; font-size: 1em; font-weight: 500; color: var(--text); }
.state p { margin: 0; }
.state > :not(:last-child) { margin-bottom: 12px; }
</style>
