<script setup lang="ts">
/** The two reserved icon slots beside a panel's search: Cancel × then Save. Both appear only while the
 * panel's draft differs from what is saved, and the space stays reserved so the header never shifts.
 * Copy kept in every admin app. */
defineProps<{ dirty: boolean; saving: boolean; label: string }>();
defineEmits<{ cancel: []; save: [] }>();
</script>

<template>
  <div class="draft-actions" role="group" :aria-label="label">
    <span class="action-slot">
      <button v-if="dirty" type="button" class="admin-icon" data-test="cancel" :title="`Cancel ${label}`" :aria-label="`Cancel ${label}`" :disabled="saving" @click="$emit('cancel')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </span>
    <span class="action-slot">
      <button v-if="dirty" type="button" class="admin-icon save-icon" data-test="save" :title="`Save ${label}`" :aria-label="`Save ${label}`" :disabled="saving" :aria-busy="saving" @click="$emit('save')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 3h13l4 4v14H3V3h1zm3 0v6h10V3M7 21v-8h10v8" /></svg>
      </button>
    </span>
  </div>
</template>

<style scoped>
.draft-actions { display: flex; justify-content: flex-end; align-items: center; gap: 4px; }
.action-slot { display: grid; place-items: center; width: 36px; height: 36px; }
.save-icon { color: var(--accent); }
@media (max-width: 767px) { .action-slot { width: 44px; height: 44px; } }
</style>
