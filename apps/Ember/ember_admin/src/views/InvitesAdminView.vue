<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import InvitesPanel from "../components/admin/InvitesPanel.vue";
const route = useRoute();
const router = useRouter();
const panel = ref<InstanceType<typeof InvitesPanel> | null>(null);
function createFromLink(): void {
  if (route.query.create !== '1') return;
  panel.value?.openCreate();
  const { create: _create, ...query } = route.query;
  void router.replace({ query });
}
onMounted(createFromLink);
watch(() => route.query.create, createFromLink);
</script>
<template>
  <PageLayout class="admin-panel" title="Invites" description="Give someone access to your workspace.">
    <template #actions><button type="button" class="primary" @click="panel?.openCreate()">＋ Create invite</button></template><div class="admin-info"><div><h3>Invites work once and expire after 7 days</h3><p>New accounts receive the configured default role.</p></div></div><InvitesPanel ref="panel" :show-heading="false" drawer />
  </PageLayout>
</template>
