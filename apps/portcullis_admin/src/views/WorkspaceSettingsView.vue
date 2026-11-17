<script setup lang="ts">
import BrainConnectionForm from "../components/BrainConnectionForm.vue";
import PageLayout from "../components/PageLayout.vue";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import SidebarPagesPanel from "../components/admin/SidebarPagesPanel.vue";
import AppConfigCard from "../components/AppConfigCard.vue";
import ToolTokensCard from "../components/ToolTokensCard.vue";
</script>
<template>
  <PageLayout class="admin-panel" title="Workspace settings" description="Changes here apply to every account."><SettingsPanel /><BrainConnectionForm scope="instance" /><SidebarPagesPanel /><ToolTokensCard kind="own" title="Tool services" /><AppConfigCard />
  </PageLayout>
</template>
