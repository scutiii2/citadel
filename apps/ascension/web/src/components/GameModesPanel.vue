<script setup lang="ts">
import { useAscensionStore } from '../stores/ascension';
import EmButton from './ui/EmButton.vue';
import EmNotice from './ui/EmNotice.vue';
import EncounterPanel from './EncounterPanel.vue';
import TrialsPanel from './TrialsPanel.vue';
import ExpeditionsPanel from './ExpeditionsPanel.vue';
const store = useAscensionStore();
const emit = defineEmits<{ collection: [] }>();
const paths = [
  { id: 'hunt' as const, name: 'Wild Hunts', description: 'Find and capture wild Ascended.', detail: '3 difficulties', action: 'Explore hunts' },
  { id: 'trial' as const, name: 'Ascension Trials', description: 'Master each Ascension type.', detail: '6 type trials · No capture', action: 'View trials' },
  { id: 'expedition' as const, name: 'Expeditions', description: 'Earn rewards while you are away.', detail: '1 expedition slot', action: 'Plan expedition' },
];
</script>

<template>
  <section class="game-modes">
    <template v-if="store.activitySelection === 'hub'">
      <h2 class="page-heading">Choose your path</h2>
      <p class="page-intro">Hunt, challenge, or explore beyond the sanctuary.</p>
      <div class="mode-paths">
        <article v-for="path in paths" :key="path.id" class="mode-path" :class="path.id">
          <div class="mode-scene" aria-hidden="true" />
          <h3>{{ path.name }}</h3><p>{{ path.description }}</p><small>{{ path.detail }}</small>
          <EmButton variant="primary" @click="store.activitySelection = path.id">{{ path.action }}</EmButton>
        </article>
      </div>
      <div v-if="store.expeditionStatus?.expedition" class="expedition-summary">
        <span>{{ store.expeditionStatus.expedition.can_claim ? 'Expedition ready to claim' : 'Expedition underway' }} · {{ store.catalog?.ascendeds.find(a => a.id === store.expeditionStatus?.expedition?.ascended_id)?.name }}</span>
        <EmButton @click="store.activitySelection = 'expedition'">View expedition</EmButton>
      </div>
    </template>
    <template v-else>
      <EmButton class="mode-back" :disabled="store.busy" @click="store.activitySelection = 'hub'">← All modes</EmButton>
      <template v-if="store.activitySelection === 'hunt'">
        <h2 class="page-heading">Wild Hunts</h2><p class="page-intro">Choose your challenge. Capture chances receive no rating penalty.</p>
        <div v-if="!store.encounter" class="hunt-options" aria-label="Hunt difficulty">
          <button v-for="hunt in store.activities?.hunts" :key="hunt.id" type="button" :aria-pressed="store.huntDifficultyId === hunt.id" :disabled="store.busy" @click="store.huntDifficultyId = hunt.id">
            <strong>{{ hunt.name }}</strong><span>Recommended overall {{ hunt.recommended_min }}–{{ hunt.recommended_max }}</span>
          </button>
        </div>
        <EncounterPanel />
        <EmNotice v-if="!store.squadMembers.length">Your squad is empty. Equip an available Ascended to battle. <EmButton @click="emit('collection')">Open Collection</EmButton></EmNotice>
      </template>
      <TrialsPanel v-else-if="store.activitySelection === 'trial'" />
      <ExpeditionsPanel v-else @collection="emit('collection')" />
    </template>
  </section>
</template>

<style src="./gameModes.css" />
