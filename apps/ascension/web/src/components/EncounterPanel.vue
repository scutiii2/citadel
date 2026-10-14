<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAscensionClient, type AscendedInfo, type BattleMode, type PersonalityItem, type TrialPreparation, type HuntPreparation } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { ascendedStats, formatCountdown, titleCase } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import BattleMatchup from "./BattleMatchup.vue";
import EmButton from "./ui/EmButton.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmPanel from "./ui/EmPanel.vue";
import EmPickCard from "./ui/EmPickCard.vue";
import EmTabs from "./ui/EmTabs.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";

/** The Battle tab without a battle, in three steps: look for a wild Ascended (once the
 * cooldown is over), see it and decline for free or fight, then set the battle up (which
 * Ascended, which preset, who plays and the highest EMBLEM tier the Ascended may throw on its
 * own). Ascension needs a preset and a limit for autonomous play. It reports the step
 * (`stage`) so the page can title it. */
export type EncounterStage = "look" | "preview" | "setup";
const emit = defineEmits<{ stage: [stage: EncounterStage] }>();

const props = defineProps<{ trial?: TrialPreparation | null }>();
const store = useAscensionStore();
const client = useAscensionClient();
const now = useNowSeconds();

const modes = [
  { value: "manual", label: "Manual" },
  { value: "autonomous", label: "Autonomous" },
];
const MODE_OPTIONS = computed(() => modes.map(option => ({ ...option, disabled: store.busy })));
const PRESET_OPTIONS = [{ value: "none", label: "None equipped" }, ...[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `Preset ${n}` }))];

const rollWait = computed(() => {
  const at = store.profile?.next_roll_at ?? null;
  return at === null ? 0 : Math.max(0, at - now.value);
});
const ascendeds = computed(() => store.squadMembers.filter(a => !a.on_expedition && (!props.trial || props.trial.eligible_ascended_ids.includes(a.ascended_id))));
const squadSlots = computed(() => Array.from({ length: store.profile?.squad_size ?? 0 }, (_, i) => {
  const member = ascendeds.value[i];
  const info = store.catalog?.ascendeds.find(s => s.id === member?.ascended_id);
  return member && info ? { member, info } : null;
}));
const ready = computed(() => ascendeds.value.filter((s) => s.faint_until === null || s.faint_until <= now.value));
const resting = computed(() => ascendeds.value.filter((s) => s.faint_until !== null && s.faint_until > now.value));
const tiers = computed(() => store.catalog?.tiers ?? []);
const openSlots = computed(() => Math.max(0, squadSlots.value.length - ascendeds.value.length));
const squadSummary = computed(() => `${ready.value.length} ready · ${resting.value.length} fainted · ${openSlots.value} open ${openSlots.value === 1 ? 'slot' : 'slots'}`);
const ownedEmblems = computed(() =>
  tiers.value
    .filter((t) => (store.profile?.emblems[t.id] ?? 0) > 0)
    .map((t) => `${store.profile?.emblems[t.id]} ${titleCase(t.id)}`)
    .join(" · "),
);
/** HP, Power and Speed of an Ascended at a level and tier, for the card strip. */
const statsAt = (info: AscendedInfo, level: number, tierId: string) => ascendedStats(info, level, tiers.value.find((t) => t.id === tierId)?.stat_multiplier ?? 1);
const previewEncounter = computed(() => props.trial ? { ...props.trial.opponent, id: 'trial-preview', status: 'pending', created_at: 0 } : store.encounter);
const wildInfo = computed(() => store.catalog?.ascendeds.find(s => s.id === previewEncounter.value?.ascended_id) ?? null);

const formOpen = ref(!!props.trial);
const ascendedId = ref("");
const presetSlot = ref("none");
const battleTraits = ref<PersonalityItem[]>([]);
const traitsMessage = ref('');
watch([ascendedId, presetSlot, formOpen], async ([id, slot, open], _, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  battleTraits.value = [];
  traitsMessage.value = '';
  if (!open || !id || slot === 'none') return;
  traitsMessage.value = 'Loading personalities…';
  try {
    const preset = await client.preset(id, Number(slot));
    if (!current) return;
    battleTraits.value = preset.personalities ?? [];
    traitsMessage.value = battleTraits.value.length ? '' : preset.instance_ids.length ? 'Personality preview unavailable.' : 'No personalities equipped in this preset.';
  } catch {
    if (current) traitsMessage.value = 'Personality preview unavailable.';
  }
});
const mode = ref<BattleMode>("manual");
const emblemLimit = ref("none");
const chosen = computed(() => ready.value.find((s) => s.ascended_id === ascendedId.value) ?? null);
const chosenInfo = computed(() => store.catalog?.ascendeds.find((s) => s.id === chosen.value?.ascended_id) ?? null);
const chosenMultiplier = computed(() => tiers.value.find(t => t.id === chosen.value?.tier_id)?.stat_multiplier ?? 1);
const wildMultiplier = computed(() => tiers.value.find(t => t.id === previewEncounter.value?.tier_id)?.stat_multiplier ?? 1);
const autonomousIncomplete = computed(
  () => mode.value === "autonomous" && (presetSlot.value === "none" || (!props.trial && emblemLimit.value === "none")),
);
const canFight = computed(() => chosen.value !== null && !autonomousIncomplete.value && !store.busy &&
  (props.trial || store.activitySelection !== 'hunt' || !!huntPreparation.value));
const limitHint = computed(() => {
  if (mode.value === "manual") return "Choose an EMBLEM when you catch in manual play.";
  const index = tiers.value.findIndex((t) => t.id === emblemLimit.value);
  if (index === -1) return "Choose a limit to let your Ascended throw EMBLEMs on its own. Autonomous play needs one.";
  const names = tiers.value.slice(0, index + 1).map((t) => titleCase(t.id));
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
  return `Your Ascended may use ${list} EMBLEMs. Higher tiers stay in your wallet.`;
});
const stage = computed<EncounterStage>(() => (props.trial ? "setup" : store.encounter === null ? "look" : formOpen.value ? "setup" : "preview"));
watch(stage, (value) => emit("stage", value), { immediate: true });
// A new encounter always starts at its preview.
watch(
  () => store.encounter?.id ?? null,
  () => {
    formOpen.value = false;
  },
);

function openForm(): void {
  ascendedId.value = ready.value.some(a => a.ascended_id === ascendedId.value) ? ascendedId.value : ready.value[0]?.ascended_id ?? "";
  presetSlot.value = String(chosen.value?.default_preset_slot ?? "none");
  mode.value = "manual";
  emblemLimit.value = "none";
  formOpen.value = true;
}

function pick(id: string): void {
  if (!store.busy && ready.value.some(s => s.ascended_id === id)) {
    ascendedId.value = id;
    presetSlot.value = String(chosen.value?.default_preset_slot ?? "none");
  }
}

function setMode(value: string): void {
  if (!store.busy) mode.value = value as BattleMode;
}

const huntPreparation = ref<HuntPreparation | null>(null);
const preparingHunt = ref(false);
const previewRetry = ref(0);
watch([() => chosen.value?.ascended_id, () => store.encounter?.activity?.difficulty_id ?? store.huntDifficultyId, () => store.activitySelection, previewRetry], async ([id, difficulty, selection], _, onCleanup) => {
  let current = true; onCleanup(() => { current = false; }); huntPreparation.value = null;
  preparingHunt.value = false;
  if (props.trial || !id || selection !== 'hunt') return;
  preparingHunt.value = true;
  try { const preview = await client.prepareHunt(difficulty, id); if (current) huntPreparation.value = preview; }
  catch { if (current) store.error = 'Could not load reward preview. Select your fighter again to retry.'; }
  finally { if (current) preparingHunt.value = false; }
}, { immediate: true });
watch(ready, values => {
  if (!ascendedId.value) {
    ascendedId.value = values[0]?.ascended_id ?? '';
    presetSlot.value = String(chosen.value?.default_preset_slot ?? 'none');
  }
}, { immediate: true });

async function fight(): Promise<void> {
  if (props.trial) {
    if (canFight.value) await store.startTrial({ ascended_id: ascendedId.value, preset_slot: presetSlot.value === 'none' ? null : Number(presetSlot.value), mode: mode.value });
    return;
  }
  const current = store.encounter;
  if (current === null || !canFight.value) return;
  const view = await store.startBattle({
    encounter_id: current.id,
    ascended_id: ascendedId.value,
    preset_slot: presetSlot.value === "none" ? null : Number(presetSlot.value),
    mode: mode.value,
    emblem_limit: emblemLimit.value === "none" ? null : emblemLimit.value,
  });
  if (view !== null) formOpen.value = false;
}
</script>

<template>
  <section class="encounter-panel">
    <div v-if="!trial && store.activitySelection === 'hunt'" class="hunt-rating">
      <label v-if="stage === 'look'" class="field"><span>Ascended to bring</span><select v-model="ascendedId" :disabled="store.busy"><option v-for="member in ready" :key="member.ascended_id" :value="member.ascended_id">{{ member.name }} · Overall {{ member.overall }}</option></select></label>
      <p v-if="preparingHunt" role="status">Loading reward preview…</p>
      <EmButton v-else-if="chosen && !huntPreparation" :disabled="store.busy" @click="previewRetry++">Retry reward preview</EmButton>
      <template v-if="huntPreparation"><p>Overall {{ huntPreparation.overall }} · Recommended {{ huntPreparation.recommended_min }}–{{ huntPreparation.recommended_max }}</p><EmNotice v-if="huntPreparation.penalty_percent">{{ huntPreparation.penalty_percent }}% fewer XP, Insignia &amp; essence. Capture chance unaffected.</EmNotice><EmNotice v-else-if="huntPreparation.below_range">Below the recommended range. Rewards have no penalty.</EmNotice><p v-else class="muted">Full rewards · Capture chance unaffected</p></template>
    </div>
    <div v-if="stage === 'look'" class="split">
      <EmPanel class="look">
        <EmIcon name="battle" :size="40" class="big-icon" />
        <h3 class="em-pixel heading">Find a wild Ascended</h3>
        <p class="muted">Search for an opponent. Preview the Ascended before choosing to fight.</p>
        <EmButton variant="primary" :disabled="rollWait > 0 || store.busy" @click="store.rollEncounter()">
          <EmIcon :name="rollWait > 0 ? 'clock' : 'ascended'" />
          {{ rollWait > 0 ? `Search ready in ${formatCountdown(rollWait)}` : "Look for a wild Ascended" }}
        </EmButton>
        <p class="caption">Declining an encounter costs nothing.</p>
      </EmPanel>
      <EmPanel>
        <h3 class="em-pixel heading">Ready for battle?</h3>
        <p class="muted">Choose an Ascended that is rested and a preset that fits your plan.</p>
        <div class="facts">
          <div>
            <strong>{{ ready.length }} Ascended ready</strong>
            <p v-for="s in resting" :key="s.ascended_id" class="em-num">
              {{ s.name }} is fainted. Ready in {{ formatCountdown((s.faint_until ?? 0) - now) }}.
            </p>
            <p v-if="resting.length === 0">All rested.</p>
          </div>
          <div>
            <strong>{{ ownedEmblems || "No EMBLEMs" }}{{ ownedEmblems ? " EMBLEMs" : "" }}</strong>
            <p>Bring an EMBLEM if you hope to catch an Ascended.</p>
          </div>
        </div>
      </EmPanel>
    </div>

    <EmPanel v-else-if="stage === 'preview' && store.encounter" class="preview">
      <AscendedPreviewCard
        v-if="wildInfo"
        class="wild-card"
        :ascended="wildInfo"
        :level="store.encounter.level"
        :tier-id="store.encounter.tier_id"
        :stats="statsAt(wildInfo, store.encounter.level, store.encounter.tier_id)"
        show-level
      />
      <div class="about">
        <p class="em-eyebrow">Wild encounter</p>
        <h3 class="em-pixel name">{{ store.encounter.name }}</h3>
        <p class="level em-num">Level {{ store.encounter.level }} · <EmTierBadge :tier-id="store.encounter.tier_id" /></p>
        <p class="muted">Its personalities stay hidden until you capture it.</p>
        <div class="buttons">
          <EmButton variant="primary" :disabled="store.busy || ready.length === 0" @click="openForm"><EmIcon name="battle" /> Fight</EmButton>
          <EmButton :disabled="store.busy" @click="store.declineEncounter()"><EmIcon name="arrow" /> Decline · free</EmButton>
        </div>
        <p v-if="ascendeds.length === 0" class="caption">Your squad is empty. Add an Ascended in Collection to battle.</p>
        <p v-else-if="ready.length === 0" class="caption">All your Ascended are fainted. Wait until one is ready again.</p>
        <p v-else class="caption">The encounter waits until you choose.</p>
      </div>
    </EmPanel>

    <form v-else class="start-form" @submit.prevent="fight">
      <div class="setup-heading">
        <div><h2 class="page-heading">Prepare for battle</h2><p class="page-intro">One fighter. Your whole squad behind you.</p></div>
        <EmButton v-if="!trial" class="back-to-encounter" :disabled="store.busy" @click="formOpen = false"><EmIcon name="arrow" /> Back to encounter</EmButton>
      </div>
      <BattleMatchup class="setup-matchup" :player="chosen" :player-info="chosenInfo" :wild="previewEncounter" :wild-info="wildInfo" :player-multiplier="chosenMultiplier" :wild-multiplier="wildMultiplier" />
      <EmNotice v-if="!chosen" tone="error">{{ ready.length ? "Select a ready squad member to continue." : "No squad member is ready. Wait until one is ready again." }}</EmNotice>

      <section class="squad-section" aria-label="Choose from your squad">
        <div class="squad-heading"><h3>Choose from your squad</h3><p class="squad-summary">{{ squadSummary }}</p></div>
        <div class="squad-choices" role="radiogroup" aria-label="Your squad">
        <div v-for="(slot, index) in squadSlots" :key="slot?.member.ascended_id ?? index" class="squad-item">
          <template v-if="slot">
            <EmPickCard
              class="squad-choice"
              :selected="chosen?.ascended_id === slot.member.ascended_id"
              :disabled="store.busy || (slot.member.faint_until !== null && slot.member.faint_until > now)"
              :aria-label="slot.member.name"
              @select="pick(slot.member.ascended_id)"
            >
              <AscendedPreviewCard class="squad-face" :class="{ down: slot.member.faint_until !== null && slot.member.faint_until > now }" :ascended="slot.info" :level="slot.member.level" :tier-id="slot.member.tier_id" :stars="slot.member.stars" :stats="statsAt(slot.info, slot.member.level, slot.member.tier_id)" show-level />
              <small v-if="slot.member.faint_until !== null && slot.member.faint_until > now" class="resting">Fainted · {{ formatCountdown(slot.member.faint_until - now) }}</small>
            </EmPickCard>
          </template>
          <div v-else class="empty-slot"><span aria-hidden="true">+</span>Empty slot</div>
        </div>
        </div>
      </section>

      <EmPanel class="plan">
        <div class="plan-heading"><h3 class="em-pixel heading">Battle plan</h3><p class="caption">Set how your Ascended fights.</p></div>
        <div class="plan-fields">
          <div>
            <p class="label">Who plays?</p>
            <EmTabs :model-value="mode" class="wide" :options="MODE_OPTIONS" ariaLabel="Who plays" @update:model-value="setMode" />
            <p class="caption">{{ mode === 'manual' ? 'You choose each action.' : 'Your Ascended chooses its actions.' }}</p>
          </div>
          <div>
            <label class="field"><span>Personality preset</span><select v-model="presetSlot" name="preset" :disabled="store.busy"><option v-for="preset in PRESET_OPTIONS" :key="preset.value" :value="preset.value">{{ preset.label }}{{ Number(preset.value) === chosen?.default_preset_slot ? ' ★ Battle default' : '' }}</option></select></label>
            <p class="caption">Collected personalities guide autonomous play.</p>
            <ul v-if="battleTraits.length" class="battle-traits" aria-label="Equipped personalities"><li v-for="trait in battleTraits" :key="trait.id"><EmIcon name="ascended" :size="16" />{{ titleCase(trait.type) }}<small>Tier {{ trait.tier }}</small></li></ul>
            <p v-else-if="traitsMessage" class="caption" role="status">{{ traitsMessage }}</p>
          </div>
          <div v-if="!trial">
            <label class="field">
              <span>Autonomous EMBLEM limit</span>
              <select v-model="emblemLimit" name="limit" :disabled="mode === 'manual' || store.busy">
                <option value="none">Choose a tier</option>
                <option v-for="t in tiers" :key="t.id" :value="t.id">{{ t.id === tiers[0]?.id ? titleCase(t.id) : `Up to ${titleCase(t.id)}` }}</option>
              </select>
            </label>
            <p class="caption">{{ limitHint }}</p>
          </div>
        </div>
        <EmNotice v-if="autonomousIncomplete" class="plan-error" tone="error">{{ trial ? 'Autonomous play needs an equipped personality preset.' : 'Autonomous play needs a preset and an EMBLEM limit.' }}</EmNotice>
        <EmButton type="submit" class="begin-battle" variant="primary" :disabled="!canFight" :aria-busy="store.busy">Begin battle <EmIcon name="arrow" /></EmButton>
        <EmButton v-if="!trial" class="decline" :disabled="store.busy" @click="store.declineEncounter()">Decline encounter</EmButton>
      </EmPanel>

      <div class="battle-footer">
        <p v-if="chosen" class="xp-note"><EmIcon name="ascended" /><span>{{ trial ? chosen.name + ' earns XP on victory.' : store.activitySelection === 'hunt' ? chosen.name + ' earns XP on victory or capture.' : chosen.name + ' gets full XP if you win or capture.' }}<small>{{ trial ? 'Only matching squad members share the XP pool.' : 'The other squad members share a smaller XP pool, after any Hunt penalty.' }}</small></span></p>

      </div>
    </form>
  </section>
</template>

<style scoped src="./encounterPanel.css" />
