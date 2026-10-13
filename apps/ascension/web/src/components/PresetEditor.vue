<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAscensionClient, type PersonalityItem } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { titleCase } from "../utils/ascension";
import { personalityCategory, personalityDescription } from "../utils/personalities";
import EmButton from "./ui/EmButton.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmSwitch from "./ui/EmSwitch.vue";
import EmTabs from "./ui/EmTabs.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";
import EmToast from "./ui/EmToast.vue";

/** An Ascended's five presets: up to three personality instances each. An autonomous Ascended
 * lets one of them lead each round. */
const props = defineProps<{ ascendedId: string; ascendedName: string; personalities: PersonalityItem[] }>();
const store = useAscensionStore();
const ascensionClient = useAscensionClient();

const MAX_EQUIPPED = 3;
const SLOT_OPTIONS = [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }));

const slot = ref("1");
const chosen = ref<string[]>([]);
const saved = ref<string[]>([]);
const loading = ref(false);
const loadError = ref("");
const toastOpen = ref(false);
const toastMessage = ref("");
const dirty = computed(() => chosen.value.join(",") !== saved.value.join(","));
const full = computed(() => chosen.value.length >= MAX_EQUIPPED);
const personalityInfo = (type: string) => store.catalog?.personalities.find(p => p.id === type);
const offMood = computed(() => store.catalog?.personality_off_mood_factor);

async function load(): Promise<void> {
  const ascendedId = props.ascendedId;
  const wanted = slot.value;
  loading.value = true;
  loadError.value = "";
  try {
    const preset = await ascensionClient.preset(ascendedId, Number(wanted));
    if (ascendedId !== props.ascendedId || wanted !== slot.value) return;
    saved.value = preset.instance_ids;
    chosen.value = [...preset.instance_ids];
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

watch([() => props.ascendedId, slot], () => void load(), { immediate: true });

function toggle(id: string, on: boolean): void {
  if (on && !chosen.value.includes(id) && chosen.value.length < MAX_EQUIPPED) chosen.value = [...chosen.value, id];
  else if (!on) chosen.value = chosen.value.filter((c) => c !== id);
}

async function save(): Promise<void> {
  const slotNumber = Number(slot.value);
  const preset = await store.savePreset(props.ascendedId, slotNumber, chosen.value);
  if (preset) {
    saved.value = preset.instance_ids;
    chosen.value = [...preset.instance_ids];
    toastMessage.value = `Preset ${slotNumber} saved. ${props.ascendedName} is ready.`;
    toastOpen.value = true;
  }
}
</script>

<template>
  <section class="preset-editor">
    <div class="personality-library"><h4 class="heading em-pixel">Revealed personalities</h4>
    <EmNotice v-if="loadError" tone="error">{{ loadError }}</EmNotice>
    <p v-else-if="loading" class="muted">Loading …</p>
    <p v-else-if="personalities.length === 0" class="muted">This Ascended has no personalities yet.</p>
    <ul v-else class="choices personalities">
      <li v-for="p in personalities" :key="p.id" :class="{ selected: chosen.includes(p.id) }">
        <EmSwitch :model-value="chosen.includes(p.id)" :label="titleCase(p.type)" :disabled="loading || (!chosen.includes(p.id) && full)" @update:model-value="toggle(p.id, $event)">
          <EmTierBadge tier-id="common" :label="`Tier ${p.tier}`" class="badge" />
        </EmSwitch>
        <div class="category-tags"><span v-for="category in personalityInfo(p.type)?.categories" :key="category">{{ personalityCategory(category) }}</span><span v-if="personalityInfo(p.type)?.rules?.length">Conditional</span><strong v-if="chosen.includes(p.id)">Selected</strong></div>
        <p class="personality-description">{{ personalityDescription(personalityInfo(p.type), p.tier) }}</p>
      </li>
    </ul>

    </div>
    <aside class="preset-inspector" aria-label="Personality preset">
      <h4 class="heading em-pixel">Personality preset</h4>
          <EmTabs v-model="slot" class="slots" :options="SLOT_OPTIONS" ariaLabel="Preset slot" />
    <p class="count em-num">Preset {{ slot }} · {{ chosen.length }} of {{ MAX_EQUIPPED }} personalities equipped</p>
    <p class="hint">One equipped personality leads each autonomous round. Others contribute {{ offMood === undefined ? "at reduced strength" : `at ${Math.round(offMood * 100)}% strength` }}. These change preferences, not guaranteed actions. Conditional numbers below show this tier's effect when leading.</p>


      <h5>Selected personalities</h5>
      <ul class="selected-personalities"><li v-for="id in chosen" :key="id"><EmIcon name="ascended" /><div><strong>{{ titleCase(personalities.find(p => p.id === id)?.type ?? 'Collected personality') }}</strong><small>{{ personalities.find(p => p.id === id) ? 'Tier ' + personalities.find(p => p.id === id)!.tier : 'Load more to reveal this instance' }}</small></div><button type="button" :disabled="loading" :aria-label="'Remove personality ' + id" @click="toggle(id, false)">×</button></li></ul>
      <p v-if="chosen.length === 0" class="muted">Select personalities for this preset.</p>
      <p v-if="dirty" class="unsaved" role="status">Unsaved changes<small>Save this preset to use your selections in battle.</small></p>
      <p class="hint">Equip up to {{ MAX_EQUIPPED }} collected personalities per preset. Each card is a separate collected instance.</p>
      <EmButton variant="primary" class="save" :disabled="!dirty || store.busy || loading" @click="save"><EmIcon name="check" /> Save preset</EmButton>
    </aside>
    <EmToast :open="toastOpen" :message="toastMessage" @close="toastOpen = false" />
  </section>
</template>

<style scoped>
.preset-editor { display: grid; grid-template-columns: minmax(0, 1fr) 292px; gap: 14px; align-items: start; }
.personality-library { min-width: 0; }
.heading { margin: 0 0 14px; font-size: 14px; }
.preset-inspector { display: flex; flex-direction: column; gap: 12px; padding: 14px; border: 1px solid var(--em-border); background: linear-gradient(135deg, var(--em-panel), var(--em-bg)); }
.preset-inspector .heading { margin-bottom: 0; }
.preset-inspector h5 { font-size: 11px; text-transform: uppercase; color: var(--em-muted); margin: 0; }
.slots { display: flex; }
.slots :deep(.tab) { flex: 1; min-width: 0; padding-inline: 8px; }
.count { font-size: 12px; color: var(--em-muted); margin: 0; }
.choices { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; list-style: none; }
.choices li { padding: 14px; border: 1px solid var(--em-border); background: linear-gradient(135deg, var(--em-panel), var(--em-bg)); }
.choices li.selected { border-color: var(--em-accent); box-shadow: inset 3px 0 var(--em-accent); }
.personality-description { color: var(--em-muted); font-size: 12px; margin: 8px 0 0; }
.category-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; color: var(--em-muted); font-size: 11px; }
.category-tags strong { color: var(--em-accent); }
.badge { margin-left: auto; }
.hint { font-size: 11px; color: var(--em-muted); margin: 0; line-height: 1.6; }
.selected-personalities { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
.selected-personalities li { display: flex; align-items: center; gap: 10px; padding: 8px; border: 1px solid var(--em-border); background: var(--em-bg); }
.selected-personalities li > div { flex: 1; min-width: 0; }
.selected-personalities strong { font-size: 12px; }
.selected-personalities small { display: block; color: var(--em-muted); font-size: 10px; }
.selected-personalities button { min-width: 32px; min-height: 36px; border: 1px solid var(--em-border); background: var(--em-panel); color: var(--em-accent); font-size: 20px; cursor: pointer; }
.unsaved { padding: 10px; border: 1px solid var(--em-accent); background: color-mix(in srgb, var(--em-accent) 12%, var(--em-bg)); font-size: 12px; color: var(--em-accent); margin: 0; }
.unsaved small { display: block; margin-top: 4px; color: var(--em-muted); font-size: 11px; }
.save { width: 100%; }
@media (max-width: 1100px) { .preset-editor { grid-template-columns: minmax(0, 1fr); } }
</style>
