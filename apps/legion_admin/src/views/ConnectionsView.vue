<script setup lang="ts">
import { agentsAdminClient } from "../api/AgentsAdminClient";

const { gatewaySettings, setGatewaySettings, decisionGatewaySettings, setDecisionGatewaySettings } = agentsAdminClient;
import GatewayConnectionCard from "../components/GatewayConnectionCard.vue";
import ModelNamesCard from "../components/ModelNamesCard.vue";
import TreasuryAddressCard from "../components/TreasuryAddressCard.vue";
import PageLayout from "../components/PageLayout.vue";
import "../components/infoPage.css";
</script>

<template>
  <PageLayout
    class="info-content connections"
    title="Connections"
    description="Where Legion reaches the two model gateways. They hold the model provider keys; Legion holds only an address and a token for each."
  >
    <div class="cards">
      <GatewayConnectionCard
        id="conversation-gateway"
        title="ConversationGateway (chat models)"
        example="http://conversationgateway:29407"
        :load="gatewaySettings"
        :store="setGatewaySettings"
      />
      <GatewayConnectionCard
        id="decision-gateway"
        title="DecisionGateway (Laya and Jev)"
        example="http://decisiongateway:29406"
        :load="decisionGatewaySettings"
        :store="setDecisionGatewaySettings"
      />
      <TreasuryAddressCard />
      <ModelNamesCard />
    </div>
  </PageLayout>
</template>

<style scoped>
.cards { display: grid; gap: 16px; }
</style>
