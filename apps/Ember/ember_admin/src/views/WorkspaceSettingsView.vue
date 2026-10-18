<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import SidebarPagesPanel from "../components/admin/SidebarPagesPanel.vue";
</script>
<template>
  <PageLayout class="admin-panel" title="Workspace settings" description="Changes here apply to every account."><SettingsPanel /><SidebarPagesPanel />
  </PageLayout>
</template>
