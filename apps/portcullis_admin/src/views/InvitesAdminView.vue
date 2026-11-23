<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import InvitesPanel from "../components/admin/InvitesPanel.vue";

const route = useRoute();
const router = useRouter();
const panel = ref<InstanceType<typeof InvitesPanel> | null>(null);
/** `?create=1` (the Accounts and Overview links) opens the create drawer, then leaves the address clean. */
function createFromLink(): void {
  if (route.query.create !== "1") return;
  panel.value?.openCreate();
  const { create: _create, ...query } = route.query;
  void router.replace({ query });
}
onMounted(createFromLink);
watch(() => route.query.create, createFromLink);
</script>

<template>
  <PageLayout class="admin-panel" title="Invites" wide>
    <InvitesPanel ref="panel" />
  </PageLayout>
</template>

<style scoped>
</style>
