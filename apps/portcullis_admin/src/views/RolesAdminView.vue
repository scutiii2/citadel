<script setup lang="ts">
import { PageLayout } from "@citadel/ui";
import { onBeforeRouteLeave } from "vue-router";
import { ref } from "vue";
import RolesPanel from "../components/admin/RolesPanel.vue";

const panel = ref<InstanceType<typeof RolesPanel> | null>(null);
onBeforeRouteLeave(() => panel.value?.confirmDiscard() ?? true);
</script>

<template>
  <PageLayout class="admin-panel" title="Roles &amp; permissions" wide>
    <RolesPanel ref="panel" />
  </PageLayout>
</template>
