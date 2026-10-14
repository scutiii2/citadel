<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useAscensionStore } from '../stores/ascension';
import { formatCountdown } from '../utils/ascension';
import AscendedPreviewCard from './AscendedPreviewCard.vue';
import EmPickCard from './ui/EmPickCard.vue';
import EmButton from './ui/EmButton.vue';
import EmNotice from './ui/EmNotice.vue';
import EmBar from './ui/EmBar.vue';
const store = useAscensionStore();
const emit = defineEmits<{ collection: [] }>();
const hours = ref(2); const chosenId = ref(''); const tick = ref(performance.now());
const expedition = computed(() => store.expeditionStatus?.expedition ?? null);
const serverNow = computed(() => (store.expeditionStatus?.server_now ?? store.profile?.server_now ?? 0) + Math.max(0, tick.value - store.expeditionObservedAt) / 1000);
const remaining = computed(() => Math.max(0, (expedition.value?.ends_at ?? 0) - serverNow.value));
const artInfo = computed(() => store.catalog?.ascendeds.find(a => a.id === expedition.value?.ascended_id));
const member = computed(() => store.profile?.ascendeds.find(a => a.ascended_id === expedition.value?.ascended_id));
const eligible = computed(() => store.profile?.ascendeds.filter(a => !a.on_expedition && !a.fainted) ?? []);
const settings = computed(() => store.activities?.expeditions);
const ready = computed(() => !!expedition.value && remaining.value <= 0);
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { timer = setInterval(() => { tick.value = performance.now(); }, 1000); void store.refreshExpedition(); });
onBeforeUnmount(() => clearInterval(timer));
watch(ready, value => { if (value) void store.refreshExpedition(); });
watch(eligible, values => { if (!values.some(a => a.ascended_id === chosenId.value)) chosenId.value = values[0]?.ascended_id ?? ''; }, { immediate: true });
async function claim(): Promise<void> { if (expedition.value && !(await store.claimExpedition(expedition.value.id))) await store.refreshExpedition(); }
</script>

<template>
  <section class="expedition-screen">
    <h2 class="page-heading">Expeditions</h2><p class="page-intro">Send one Ascended to earn XP and Insignia while you are away.</p>
    <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>
    <div v-if="expedition" class="expedition-active">
      <AscendedPreviewCard v-if="artInfo && member" :ascended="artInfo" :level="member.level" :tier-id="member.tier_id" :stars="member.stars" show-level />
      <div class="expedition-details">
        <h3>{{ artInfo?.name ?? expedition.ascended_id }}</h3><p>{{ ready ? 'Ready to claim' : 'On expedition' }} · {{ expedition.duration_hours }} hours</p>
        <strong class="expedition-timer em-num">{{ ready ? 'Expedition complete' : formatCountdown(remaining) }}</strong>
        <EmBar :value="expedition.duration_hours * 3600 - remaining" :max="expedition.duration_hours * 3600" label="Expedition progress" />
        <p>Rewards: {{ expedition.xp_reward }} XP · {{ expedition.insignia_reward }} Insignia</p>
        <p class="muted">Unavailable for battle. Squad, upgrades, and loadout changes are locked until rewards are claimed.</p>
        <EmButton variant="primary" :disabled="!ready || store.busy" @click="claim">Claim &amp; Return</EmButton>
        <p v-if="!ready" class="muted">Available when the expedition ends · 1 / 1 slot occupied</p>
      </div>
    </div>
    <template v-else>
      <EmNotice v-if="store.expeditionReceipt">Returned with {{ store.expeditionReceipt.xp }} XP and {{ store.expeditionReceipt.insignia }} Insignia. Equip your Ascended in Collection when you are ready.</EmNotice>
      <div class="expedition-durations" aria-label="Expedition duration"><EmButton v-for="duration in settings?.durations_hours" :key="duration" :variant="hours === duration ? 'primary' : undefined" :aria-pressed="hours === duration" :disabled="store.busy" @click="hours = duration">{{ duration }} hours</EmButton></div>
      <p class="activity-facts">Expected rewards: {{ hours * (settings?.xp_per_hour ?? 0) }} XP · {{ hours * (settings?.insignia_per_hour ?? 0) }} Insignia</p>
      <div class="expedition-choices" role="radiogroup" aria-label="Ascended to send">
        <div v-for="a in eligible" :key="a.ascended_id">
          <EmPickCard :selected="chosenId === a.ascended_id" :disabled="store.busy" :aria-label="a.name" @select="chosenId = a.ascended_id"><AscendedPreviewCard v-if="store.catalog?.ascendeds.find(info => info.id === a.ascended_id)" :ascended="store.catalog!.ascendeds.find(info => info.id === a.ascended_id)!" :level="a.level" :tier-id="a.tier_id" :stars="a.stars" show-level /></EmPickCard>
          <p class="muted">{{ a.in_squad ? 'Currently in squad' : 'Outside squad' }}</p>
        </div>
      </div>
      <EmNotice v-if="!eligible.length">No rested Ascended available.</EmNotice>
      <EmNotice v-if="store.profile?.active_battle">Finish your active battle before sending an expedition.</EmNotice>
      <p class="muted">Departure removes this Ascended from your squad and locks battle use, upgrades, and loadout changes until you claim its rewards. No early recall.</p>
      <EmButton variant="primary" :disabled="!chosenId || store.busy || !!store.profile?.active_battle" @click="store.startExpedition(chosenId, hours)">Send on expedition</EmButton>
    </template>
    <EmNotice v-if="!store.squadMembers.length">Your squad is empty. <EmButton @click="emit('collection')">Open Collection</EmButton></EmNotice>
  </section>
</template>
