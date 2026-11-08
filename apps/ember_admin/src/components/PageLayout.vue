<script setup lang="ts">
// Shared component copies: apply future fixes in both ember_web and ember_admin.
defineProps<{
  title: string;
  description?: string;
  wide?: boolean;
  /** Keep workspace panels in the view height so their own lists can scroll. */
  fill?: boolean;
}>();
</script>

<template>
  <section class="page info-page" :class="{ 'page-layout-fill': fill }">
    <div class="page-column" :class="{ 'page-column-wide': wide }">
      <header class="page-head">
        <div class="page-head-copy">
          <h2 class="page-title">{{ title }}</h2>
          <p v-if="description" class="page-description">{{ description }}</p>
        </div>
        <div v-if="$slots.actions" class="page-actions"><slot name="actions" /></div>
      </header>
      <div v-if="$slots.toolbar" class="page-toolbar"><slot name="toolbar" /></div>
      <slot />
    </div>
  </section>
</template>
