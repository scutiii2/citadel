<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import ToolTokensCard from "../components/ToolTokensCard.vue";
import "../components/infoPage.css";
</script>

<template>
  <PageLayout
    class="info-content tool-services"
    title="Tool services"
    description="The tokens Stronghold presents to Bard, Scribe and Reader when a chat uses speech, audio or documents."
  >
    <ToolTokensCard kind="stronghold" title="Stronghold's tokens" />
  </PageLayout>
</template>
