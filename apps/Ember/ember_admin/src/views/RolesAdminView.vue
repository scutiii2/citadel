<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { onBeforeRouteLeave } from "vue-router";
import { ref } from "vue";
import RolesPanel from "../components/admin/RolesPanel.vue";
import { useAuthStore } from "../stores/auth";
const auth = useAuthStore();
const panel = ref<InstanceType<typeof RolesPanel> | null>(null);
onBeforeRouteLeave(() => panel.value?.confirmDiscard() ?? true);
</script>
<template>
  <PageLayout class="admin-panel roles-page" title="Roles &amp; permissions" description="Make access easy to understand and maintain." fill>
    <template #actions><button v-if="auth.hasPermission('roles.manage')" type="button" class="primary" @click="panel?.openCreate()">＋ New role</button></template><RolesPanel ref="panel" :show-heading="false" />
  </PageLayout>
</template>

<style scoped>
.roles-page { display: flex; flex: 1; flex-direction: column; min-height: 0; }
</style>
