<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useAscensionStore } from '../stores/ascension';
import { typeLabel } from '../utils/ascensionTypes';
import TypeSymbol from './ui/TypeSymbol.vue';
import EmButton from './ui/EmButton.vue';
import EmNotice from './ui/EmNotice.vue';
import EncounterPanel from './EncounterPanel.vue';
const store = useAscensionStore();
const stages = computed(() => store.trials?.trials.find(t => t.type_id === store.trialTypeId)?.stages ?? []);
async function choose(typeId: string, stage = 1): Promise<void> { await store.prepareTrial(typeId, stage); }
onMounted(async () => { await store.loadTrials(); await choose(store.trialTypeId, store.trialStage); });
</script>

<template>
  <section class="trial-screen">
    <h2 class="page-heading">Ascension Trials</h2><p class="page-intro">Only matching Ascended can fight. Win a stage to unlock the next.</p>
    <div class="trial-types" aria-label="Ascension type">
      <EmButton v-for="id in store.activities?.trial_types" :key="id" :variant="store.trialTypeId === id ? 'primary' : undefined" :aria-pressed="store.trialTypeId === id" :disabled="store.busy" @click="choose(id)"><TypeSymbol :type-id="id" :size="24" decorative />{{ typeLabel(id) }}</EmButton>
    </div>
    <div class="trial-stages" aria-label="Trial stages">
      <EmButton v-for="stage in stages" :key="stage.stage" :disabled="!stage.unlocked || store.busy" :aria-pressed="store.trialStage === stage.stage" @click="choose(store.trialTypeId, stage.stage)">Stage {{ stage.stage }} {{ stage.cleared ? '✓' : stage.unlocked ? '' : '🔒' }}</EmButton>
    </div>
    <template v-if="store.trialPreparation">
      <p class="activity-facts">{{ typeLabel(store.trialTypeId) }} Trial · Stage {{ store.trialStage }} · No capture · {{ store.trialPreparation.first_clear ? 'First-clear rewards ×2' : 'Replay rewards' }}</p>
      <p v-if="store.trialPreparation.rewards" class="activity-facts">Rewards: {{ store.trialPreparation.rewards.xp }} XP · {{ store.trialPreparation.rewards.insignia }} Insignia · {{ store.trialPreparation.rewards.essence }} {{ store.trialPreparation.rewards.essence_tier_id }} essence</p>
      <EmNotice v-if="!store.trialPreparation.unlocked">Win the previous stage first.</EmNotice>
      <EmNotice v-else-if="!store.trialPreparation.eligible_ascended_ids.length">{{ store.trialPreparation.reason }}</EmNotice>
      <EncounterPanel v-else :key="store.trialTypeId + store.trialStage" :trial="store.trialPreparation" />
    </template>
    <p v-else role="status">Loading Trial preparation…</p>
  </section>
</template>
