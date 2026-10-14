<script setup lang="ts">
import type { AscendedInfo, OwnedAscended } from '../api/AscensionClient';
import { titleCase, passiveText, abilityEffect } from '../utils/ascension';
import EmBar from './ui/EmBar.vue';
import EmButton from './ui/EmButton.vue';
import EmEmblem from './ui/EmEmblem.vue';
import EmEssence from './ui/EmEssence.vue';
import EmIcon from './ui/EmIcon.vue';
import EmTierBadge from './ui/EmTierBadge.vue';

defineProps<{ ascended: OwnedAscended; info: AscendedInfo | null; essence: number; busy: boolean; message: string }>();
defineEmits<{ addStar: []; raiseTier: [] }>();
</script>

<template>
  <section class="progression-tab" role="tabpanel" aria-label="Progression">
    <div class="progression-panel">
      <header class="progression-heading"><h3>{{ ascended.next_tier_id ? `Path to ${titleCase(ascended.next_tier_id)}` : 'Star progression' }}</h3><p>Strengthen {{ ascended.name }} through stars and ascension.</p></header>
      <div class="progression-resources" aria-label="Upgrade resources">
        <div><EmIcon name="book" :size="30" /><span>Spare copies<strong class="em-num">{{ ascended.copies }}</strong></span></div>
        <div><EmEssence :tier-id="ascended.tier_id" :size="38" /><span>{{ titleCase(ascended.tier_id) }} essence<strong class="em-num">{{ essence }}</strong></span></div>
      </div>
      <div class="upgrade">
        <template v-if="ascended.stars_needed !== null">
          <div class="star-journey" :class="{ 'has-target': ascended.next_tier_id }">
            <div class="journey-tier"><EmEmblem :tier-id="ascended.tier_id" :size="56" /><EmTierBadge :tier-id="ascended.tier_id" /></div>
            <div v-if="ascended.stars_needed <= 10" class="milestones" role="img" :aria-label="`${ascended.stars} of ${ascended.stars_needed} stars`"><span v-for="n in ascended.stars_needed" :key="n" class="milestone" :class="{ earned: n <= ascended.stars }"><EmIcon name="ascended" :size="36" /></span></div>
            <EmBar v-else :value="ascended.stars" :max="ascended.stars_needed" :label="ascended.name + ' stars'" />
            <div v-if="ascended.next_tier_id" class="journey-tier next"><EmEmblem :tier-id="ascended.next_tier_id" :size="56" /><span>{{ titleCase(ascended.next_tier_id) }}</span></div>
          </div>
          <p class="journey-caption em-num">Stars {{ ascended.stars }} / {{ ascended.stars_needed }}<template v-if="ascended.next_tier_id"> to reach {{ titleCase(ascended.next_tier_id) }}</template></p>
          <div class="upgrade-columns">
            <section class="next-star">
              <h4>{{ ascended.stars >= ascended.stars_needed ? 'Stars complete' : 'Add your next star' }}</h4>
              <template v-if="ascended.stars < ascended.stars_needed">
                <p class="cost-head">A star costs</p>
                <ul class="star-cost">
                  <li :class="{ met: ascended.copies >= 1 }"><EmIcon :name="ascended.copies >= 1 ? 'check' : 'warning'" /><span>1 spare copy</span><small>You have {{ ascended.copies }}</small></li>
                  <li :class="{ met: essence >= ascended.star_essence_cost }"><EmEssence :tier-id="ascended.tier_id" :size="24" /><span>{{ ascended.star_essence_cost }} {{ titleCase(ascended.tier_id) }} essence</span><small>You have {{ essence }}</small></li>
                </ul>
                <EmButton variant="primary" :disabled="!ascended.can_star_up || busy" :aria-busy="busy" @click="$emit('addStar')">Add a star</EmButton>
              </template>
              <p v-else class="muted">Maximum stars reached</p>
            </section>
            <section v-if="ascended.next_tier_id" class="next-ascension">
              <h4>Next ascension</h4><EmEmblem :tier-id="ascended.next_tier_id" :size="72" /><strong>{{ titleCase(ascended.next_tier_id) }}</strong>
              <EmButton :variant="ascended.can_tier_up ? 'primary' : 'secondary'" :disabled="!ascended.can_tier_up || busy" :aria-busy="busy" @click="$emit('raiseTier')">Raise to {{ titleCase(ascended.next_tier_id) }}</EmButton>
              <p v-if="!ascended.can_tier_up">Reach {{ ascended.stars_needed }} stars first.</p>
            </section>
          </div>
        </template>
        <p v-else class="ladder-complete"><EmTierBadge :tier-id="ascended.tier_id" />Top of its ladder: no more stars.</p>
        <p v-if="message" class="upgrade-note" role="status">{{ message }}</p>
      </div>
    </div>
    <aside class="progression-side">
      <h3>Level progress</h3>
      <p class="level-progress"><EmIcon name="shield" :size="28" /><strong>Level {{ ascended.level }}</strong><span>/ {{ ascended.level_cap }}</span></p>
      <template v-if="ascended.xp_needed !== null"><EmBar :value="ascended.xp" :max="ascended.xp_needed" :label="ascended.name + ' XP'" /><p class="muted em-num">{{ ascended.xp }} / {{ ascended.xp_needed }} XP</p><p class="level-hint">Earn experience in battle.</p></template>
      <p v-else class="muted">Highest level reached</p>
      <img v-if="info?.art.main_card" class="progression-art" :src="info.art.main_card" alt="" draggable="false" />
      <div v-if="info" class="foundation-summary"><h4>Innate passive</h4><strong>{{ titleCase(info.passive.kind) }}</strong><p>{{ passiveText(info.passive.kind, info.passive.params) }}</p><h4>Foundation abilities</h4><article v-for="ability in info.abilities" :key="ability.id"><strong>{{ ability.name }}</strong><p>{{ abilityEffect(ability) }} · Level {{ ability.unlock_level }}</p></article></div>
    </aside>
  </section>
</template>

<style scoped src="./ascendedProgression.css" />
