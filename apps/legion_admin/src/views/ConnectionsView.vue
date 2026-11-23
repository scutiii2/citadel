<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useRoute } from "vue-router";
import ModelGatewayTable from "../components/ModelGatewayTable.vue";
import PageLayout from "../components/PageLayout.vue";
import ServersView from "./ServersView.vue";

const route = useRoute();
const servers = ref<InstanceType<typeof ServersView>>();
const gateways = [
  { kind: "conversation", title: "Chat models", help: "The chat models Legion's agents talk to, built into Legion. Add a gateway with + and give it the provider, model and key; the key is kept in Legion's database and never shown again. Test checks that it answers." },
  { kind: "decision", title: "Decision models", help: "The models that answer Legion's routing and classification questions (Laya, Jev). Add a gateway with + and test it. Name them laya and jev for Legion to use them." },
] as const;

watch(() => route.hash, async (hash) => {
  if (hash !== "#mcp-servers") return;
  await nextTick();
  servers.value?.focusPanel();
}, { immediate: true, flush: "post" });
</script>

<template>
  <PageLayout class="connections" title="Connections" wide>
    <ModelGatewayTable v-for="gateway in gateways" :key="gateway.kind" v-bind="gateway" />
    <ServersView ref="servers" />
  </PageLayout>
</template>

