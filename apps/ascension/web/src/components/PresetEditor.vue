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
const props = defineProps<{ ascendedId: string; ascendedName: string; personalities: PersonalityItem[]; defaultSlot?: number }>();
const emit = defineEmits<{ saved: [] }>();
const store = useAscensionStore();
const ascensionClient = useAscensionClient();

const MAX_EQUIPPED = 3;
const SLOT_OPTIONS = computed(() => [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n), disabled: loading.value || store.busy || (dirty.value && String(n) !== slot.value) })));

const slot = ref(String(props.defaultSlot ?? 1));
const query = ref("");
const category = ref("all");
const resolved = ref<PersonalityItem[]>([]);
const knownPersonalities = computed(() => [...props.personalities, ...resolved.value.filter(p => !props.personalities.some(item => item.id === p.id))]);
const chosenItems = computed(() => chosen.value.map(id => ({ id, item: knownPersonalities.value.find(p => p.id === id) })));
const categories = computed(() => [...new Set(props.personalities.flatMap(p => personalityInfo(p.type)?.categories ?? []))]);
const filtered = computed(() => props.personalities.filter(p => titleCase(p.type).toLowerCase().includes(query.value.trim().toLowerCase()) && (category.value === 'all' || personalityInfo(p.type)?.categories.includes(category.value))));
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
let loadRequest = 0;

async function load(): Promise<void> {
  const request = ++loadRequest;
  const ascendedId = props.ascendedId;
  const wanted = slot.value;
  loading.value = true;
  loadError.value = "";
  try {
    const preset = await ascensionClient.preset(ascendedId, Number(wanted));
    if (request !== loadRequest || ascendedId !== props.ascendedId || wanted !== slot.value) return;
    resolved.value = preset.personalities ?? [];
    saved.value = preset.instance_ids;
    chosen.value = [...preset.instance_ids];
  } catch (err) {
    if (request === loadRequest) loadError.value = errorMessage(err);
  } finally {
    if (request === loadRequest) loading.value = false;
  }
}

watch([() => props.ascendedId, slot], () => void load(), { immediate: true });
watch(() => props.defaultSlot, value => { if (!dirty.value && value !== undefined) slot.value = String(value); });

function toggle(id: string, on: boolean): void {
  if (loading.value || store.busy || loadError.value) return;
  if (on && !chosen.value.includes(id) && chosen.value.length < MAX_EQUIPPED) chosen.value = [...chosen.value, id];
  else if (!on) chosen.value = chosen.value.filter((c) => c !== id);
}

async function save(): Promise<void> {
  if (loading.value || store.busy || loadError.value) return;
  const ascendedId = props.ascendedId;
  const slotNumber = Number(slot.value);
  const preset = await store.savePreset(ascendedId, slotNumber, chosen.value);
  if (preset && ascendedId === props.ascendedId && slotNumber === Number(slot.value)) {
    saved.value = preset.instance_ids;
    chosen.value = [...preset.instance_ids];
    toastMessage.value = `Preset ${slotNumber} saved. ${props.ascendedName} is ready.`;
    toastOpen.value = true;
    emit("saved");
  }
}
</script>

<template>
  <section class="preset-editor"><nav class="preset-rail" aria-label="Personality presets"><h4>Presets</h4><EmTabs v-model="slot" class="slots" :options="SLOT_OPTIONS" ariaLabel="Preset slot" /><p class="rail-default">★ Preset {{ defaultSlot ?? 1 }} is the battle default</p><p class="hint">Change your battle default in Overview.</p></nav>
    <div class="personality-library"><h4 class="heading em-pixel">Personality library</h4><label class="library-search"><span class="sr-only">Search personalities</span><input v-model="query" type="search" placeholder="Search personalities…" aria-label="Search personalities" /></label><div class="library-filters"><button type="button" :aria-pressed="category === 'all'" @click="category = 'all'">All</button><button v-for="item in categories" :key="item" type="button" :aria-pressed="category === item" @click="category = item">{{ personalityCategory(item) }}</button></div>
    <EmNotice v-if="loadError" tone="error">{{ loadError }}</EmNotice>
    <p v-else-if="personalities.length === 0" class="muted">This Ascended has no personalities yet.</p>
    <ul v-else class="choices personalities" :class="{ busy: loading }" :aria-busy="loading">
      <li v-for="p in filtered" :key="p.id" :class="{ selected: chosen.includes(p.id) }">
        <span class="personality-art"><EmIcon :name="p.type.includes('AGGRESS') ? 'battle' : p.type.includes('DEFEN') ? 'shield' : p.type.includes('CALM') ? 'feather' : 'ascended'" :size="38" /></span>
        <div class="personality-name"><strong>{{ titleCase(p.type) }}</strong><EmTierBadge tier-id="common" :label="`Tier ${p.tier}`" class="badge" /><div class="category-tags"><span v-for="category in personalityInfo(p.type)?.categories" :key="category">{{ personalityCategory(category) }}</span><span v-if="personalityInfo(p.type)?.rules?.length">Conditional</span></div></div>
        <p class="personality-description">{{ personalityDescription(personalityInfo(p.type), p.tier) }}</p>
        <EmSwitch :model-value="chosen.includes(p.id)" :label="chosen.includes(p.id) ? 'Selected' : 'Not selected'" :disabled="loading || store.busy || !!loadError || (!chosen.includes(p.id) && full)" :aria-label="titleCase(p.type)" @update:model-value="toggle(p.id, $event)" />
      </li>
    </ul>

    </div>
    <aside class="preset-inspector" aria-label="Personality preset">
      <h4 class="heading em-pixel">Preset {{ slot }}</h4>
      <span v-if="Number(slot) === (defaultSlot ?? 1)" class="default-label">★ Battle default</span>
    <p class="count em-num">Preset {{ slot }} · {{ chosen.length }} of {{ MAX_EQUIPPED }} personalities equipped</p>
    <p class="hint">One equipped personality leads each autonomous round. Others contribute {{ offMood === undefined ? "at reduced strength" : `at ${Math.round(offMood * 100)}% strength` }}. These change preferences, not guaranteed actions. Conditional numbers below show this tier's effect when leading.</p>


      <h5>Selected personalities</h5>
      <ul class="selected-personalities">
        <li v-for="{ id, item } in chosenItems" :key="id"><EmIcon name="ascended" /><div><strong>{{ titleCase(item?.type ?? 'Collected personality') }}</strong><small>{{ item ? 'Tier ' + item.tier : 'Load more to reveal this instance' }}</small><p v-if="item" class="equipped-effect">{{ personalityDescription(personalityInfo(item.type), item.tier) }}</p></div><button type="button" :disabled="loading || store.busy || !!loadError" :aria-label="'Remove personality ' + id" @click="toggle(id, false)">×</button></li>
        <li v-for="index in Math.max(0, MAX_EQUIPPED - chosen.length)" :key="'empty-' + index" class="empty-personality"><EmIcon name="ascended" /><small>Empty personality slot</small></li>
      </ul>
      <p v-if="chosen.length === 0" class="muted">Select personalities for this preset.</p>
      <p v-if="dirty" class="unsaved" role="status">Unsaved changes<small>Save this preset to use your selections in battle.</small><button class="discard" type="button" :disabled="store.busy" @click="chosen = [...saved]">Discard changes</button></p>
      <p class="hint">Equip up to {{ MAX_EQUIPPED }} collected personalities per preset. Each card is a separate collected instance.</p>
      <EmButton variant="primary" class="save" :disabled="!dirty || store.busy || loading || !!loadError" @click="save"><EmIcon name="check" /> Save preset</EmButton>
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
.slots { display: flex; }.slots :deep(.tab.active){background:linear-gradient(#fac88a,#de9655);border:1px solid #f5b56f;color:#15222e;box-shadow:inset 0 1px #ffdeb0;}.preset-inspector :deep(.em-button.primary:not(:disabled)){background:linear-gradient(#fac88a,#de9655);border-color:#f5b56f;box-shadow:inset 0 1px #ffdeb0;}
.slots :deep(.tab) { flex: 1; min-width: 0; padding-inline: 8px; }
.count { font-size: 12px; color: var(--em-muted); margin: 0; }
.choices { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; list-style: none; }
.choices { transition: opacity 150ms ease 250ms; }
.choices.busy { opacity: 0.6; }
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

.preset-editor{grid-template-columns:minmax(0,1fr) 310px;gap:12px;}.personality-library{border:1px solid var(--em-border);padding:12px;background:linear-gradient(120deg,#102735,#091c29);}.heading{font-size:12px;}.choices li{display:grid;grid-template-columns:54px 115px minmax(0,1fr) 108px;gap:12px;align-items:center;padding:8px;background:linear-gradient(120deg,#173243,#0c2330);}.personality-art{width:52px;height:58px;display:grid;place-items:center;border:1px solid var(--em-border);background:#0b1c28;color:var(--em-accent);box-shadow:inset 0 0 0 3px #0004;}.personality-name{display:flex;flex-direction:column;gap:6px;font-size:12px;}.personality-description{margin:0;border-inline:1px solid var(--em-border);padding:5px 12px;line-height:1.6;font-size:11px;}.category-tags{font-size:9px;margin:0;gap:4px;}.badge{margin:0;}.choices :deep(.em-switch){font-size:10px;gap:6px;}.choices :deep(.track){width:24px;height:24px;padding:0;border-radius:var(--em-radius);}.choices :deep(.thumb){display:none;}.choices :deep(.input:checked + .track){background:linear-gradient(#fac488,#de9759);}.choices :deep(.input:checked + .track::after){content:'✓';color:#182633;font-size:19px;font-weight:900;margin:auto;}.choices :deep(.input:checked ~ .label){color:var(--em-accent);}.preset-inspector{background:linear-gradient(120deg,#102735,#091c29);border-radius:var(--em-radius);}.preset-inspector .hint{font-size:10px;}.selected-personalities li{background:#102735;}.unsaved{background:#6d293233;border-color:#a65c61;color:#f7846e;}.save{min-height:42px;}
@media(max-width:1200px){.choices li{grid-template-columns:42px 95px minmax(0,1fr);gap:8px;}.personality-art{width:40px;}.choices :deep(.em-switch){grid-column:2 / -1;min-height:30px;}.personality-description{font-size:10px;padding-inline:8px;}}
@media(max-width:950px){.preset-editor{grid-template-columns:minmax(0,1fr);}}
@media(max-width:650px){.choices li{grid-template-columns:42px minmax(0,1fr);}.personality-description{grid-column:1 / -1;border:0;padding:0;font-size:12px;}.choices :deep(.em-switch){grid-column:1 / -1;}.personality-library{padding:10px;}}

</style>

<style scoped src="./presetEditor.css" />
