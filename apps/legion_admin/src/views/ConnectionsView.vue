<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useRoute } from "vue-router";
import AdminSearch from "../components/admin/AdminSearch.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import ModelGatewayTable from "../components/ModelGatewayTable.vue";
import PageLayout from "../components/PageLayout.vue";
import ServersView from "./ServersView.vue";

const route = useRoute();
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const servers = ref<InstanceType<typeof ServersView>>();
const gateways = [
  { kind: "conversation", title: "Chat models" },
  { kind: "decision", title: "Decision models" },
] as const;
const shown = ref<Record<string, boolean>>({});

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
        <div class="admin-panel-tools"><PanelHelp title="Model gateways">The models Legion sends requests to, built into Legion. Add a gateway, give it the provider key (or env:NAME to read it from Legion's environment), and test it. Chat models serve the agents' conversations; decision models answer routing and classification questions.</PanelHelp><AdminSearch ref="searchField" v-model="search" label="Search model gateways" /></div>
      </header>
      <ModelGatewayTable v-for="gateway in gateways" :key="gateway.kind" :kind="gateway.kind" :title="gateway.title"
        :search="search" :fallback-focus="() => searchField?.focus()" @visible="shown[gateway.kind] = $event" />
      <p v-if="gateways.every(({ kind }) => shown[kind] === false)">No gateways match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
    </section>
    <ServersView ref="servers" />
  </PageLayout>
</template>

<style scoped>
.admin-panel-card { margin-bottom: 14px; }
</style>
