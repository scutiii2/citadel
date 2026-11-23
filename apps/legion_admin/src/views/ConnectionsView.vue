<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import AdminSearch from "../components/admin/AdminSearch.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import GatewayConnectionCard from "../components/GatewayConnectionCard.vue";
import PageLayout from "../components/PageLayout.vue";
import ServersView from "./ServersView.vue";

const route = useRoute();
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const matches = ref<Record<string, boolean>>({});
const servers = ref<InstanceType<typeof ServersView>>();
const gateways = [
  { id: "conversation-gateway", title: "ConversationGateway", example: "http://conversation-gateway:29407",
    load: agentsAdminClient.gatewaySettings, store: agentsAdminClient.setGatewaySettings },
  { id: "decision-gateway", title: "DecisionGateway", example: "http://decision-gateway:29406",
    load: agentsAdminClient.decisionGatewaySettings, store: agentsAdminClient.setDecisionGatewaySettings },
];

watch(() => route.hash, async (hash) => {
  if (hash !== "#mcp-servers") return;
  await nextTick();
  servers.value?.focusPanel();
}, { immediate: true, flush: "post" });
</script>

<template>
  <PageLayout class="connections" title="Connections" wide>
    <section class="admin-panel-card" aria-labelledby="model-gateways">
      <header class="admin-panel-head">
        <h2 id="model-gateways">Model gateways</h2>
        <div class="admin-panel-tools"><PanelHelp title="Model gateways">The model gateways Legion sends requests to. Open one to edit its description and address.</PanelHelp><AdminSearch ref="searchField" v-model="search" label="Search model gateways" /></div>
      </header>
      <div class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="model-gateways">
        <table class="admin-records">
          <thead><tr><th scope="col">Name</th><th scope="col">Connection URL</th></tr></thead>
          <tbody>
            <GatewayConnectionCard v-for="gateway in gateways" :key="gateway.id" v-bind="gateway"
              :search="search" :fallback-focus="() => searchField?.focus()" @visible="matches[gateway.id] = $event" />
            <tr v-if="gateways.every(({ id }) => matches[id] === false)">
              <td colspan="2">No gateways match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <ServersView ref="servers" />
  </PageLayout>
</template>

<style scoped>
.admin-panel-card { margin-bottom: 14px; }
</style>
