<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import SidebarPagesPanel from "../components/admin/SidebarPagesPanel.vue";
import AppConfigCard from "../components/AppConfigCard.vue";
</script>

<template>
  <PageLayout class="admin-panel" title="Workspace settings" wide><AppConfigCard /><SidebarPagesPanel />
  </PageLayout>
</template>
