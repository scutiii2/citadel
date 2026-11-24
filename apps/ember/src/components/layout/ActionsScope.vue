<script setup lang="ts">
// Wraps a page's header actions so a PanelHelp inside knows it is the page's own help
// (the app header's Help button shows it on wide screens).
import { provide } from "vue";
import { PAGE_ACTIONS_KEY } from "../../composables/useHeaderHelp";

provide(PAGE_ACTIONS_KEY, true);
</script>

<template><slot /></template>
