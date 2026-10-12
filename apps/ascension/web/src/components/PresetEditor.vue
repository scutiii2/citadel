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
    <h4 class="heading">Personality presets</h4>
    <EmTabs v-model="slot" class="slots" :options="SLOT_OPTIONS" ariaLabel="Preset slot" />
    <p class="count em-num">Preset {{ slot }} · {{ chosen.length }} of {{ MAX_EQUIPPED }} personalities equipped</p>
    <p class="hint">One equipped personality leads each autonomous round. Others contribute {{ offMood === undefined ? "at reduced strength" : `at ${Math.round(offMood * 100)}% strength` }}. These change preferences, not guaranteed actions. Conditional numbers below show this tier's effect when leading.</p>

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

    <p class="hint">Equip up to {{ MAX_EQUIPPED }} collected personalities per preset. Each card is a separate collected instance.</p>
    <EmButton variant="primary" class="save" :disabled="!dirty || store.busy" @click="save"><EmIcon name="check" /> Save preset</EmButton>
    <EmToast :open="toastOpen" :message="toastMessage" @close="toastOpen = false" />
  </section>
</template>

<style scoped>
.preset-editor {
  display: flex;
  flex-direction: column;
  gap: var(--em-space-3);
  margin-top: 0;
}
.heading {
  margin: 0;
  font-size: 16px;
}
.slots {
  display: flex;
}
.slots :deep(.tab) {
  flex: 1;
}
.count {
  font-size: 12px;
  color: var(--em-muted);
}
.choices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--em-space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.choices li {
  padding: var(--em-space-4);
  border: 1px solid var(--em-divider);
  border-radius: var(--em-radius);
  background: var(--em-bg);
}
.choices li.selected { border-color: var(--em-accent); }
.personality-description { color: var(--em-muted); font-size: 13px; margin-top: var(--em-space-2); }
.category-tags { display: flex; flex-wrap: wrap; gap: var(--em-space-2); color: var(--em-muted); font-size: 12px; }
.category-tags strong { color: var(--em-accent); }
.badge {
  margin-left: auto;
}
.hint {
  padding: 10px 14px;
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  background: var(--em-bg);
  font-size: 12px;
  color: var(--em-muted);
}
.save {
  align-self: flex-end;
}
@media (max-width: 700px) { .choices { grid-template-columns: 1fr; } }
</style>
