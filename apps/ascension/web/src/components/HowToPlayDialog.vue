<script setup lang="ts">
import EmButton from "./ui/EmButton.vue";
import EmDialog from "./ui/EmDialog.vue";
import EmIcon from "./ui/EmIcon.vue";

defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <EmDialog :open="open" title="Keep the fire going" @close="emit('close')">
    <ol class="rules">
      <li><strong>Choose a starter.</strong> Guardian, Scout or Striker begins your collection.</li>
      <li><strong>Find a wild Ascended.</strong> Preview it, then fight or decline for free.</li>
      <li><strong>Make your move.</strong> Play manually or let your Ascended act autonomously.</li>
      <li><strong>Throw an EMBLEM.</strong> Choose a permitted tier before the five-second timer ends.</li>
      <li><strong>Forge your collection.</strong> Earn XP, Insignia and essence; spare copies and essence add stars, and stars raise tiers. Levels cap at 30, or 50 for Forbidden.</li>
    </ol>
    <EmButton variant="primary" class="ready" @click="emit('close')"><EmIcon name="play" /> Ready to play</EmButton>
  </EmDialog>
</template>

<style scoped>
.rules { margin: 0 0 20px; padding-left: 22px; color: var(--em-muted); }
.rules li { padding: 8px 0; }
.rules strong { color: var(--em-text); }
.ready { width: 100%; }
</style>
