<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAscensionClient, type OwnedAscended, type PersonalityItem, type TreeView } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { ASCENSION_TYPES, groupByType, typeLabel, typesPresent } from "../utils/ascensionTypes";
import { ascendedStats, formatCountdown, titleCase, passiveText, abilityEffect } from "../utils/ascension";
import { useNowSeconds } from "../composables/useNowSeconds";
import TreeTab from "./TreeTab.vue";
import PresetEditor from "./PresetEditor.vue";
import AscendedCard from "./AscendedCard.vue";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmBar from "./ui/EmBar.vue";
import EmButton from "./ui/EmButton.vue";
import EmDialog from "./ui/EmDialog.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";
import EmEssence from "./ui/EmEssence.vue";
import EmTabs from "./ui/EmTabs.vue";
import TypeSymbol from "./ui/TypeSymbol.vue";
import AbilitySlots from "./AbilitySlots.vue";

/** Collection filters, squad strip and collected cards; pressing a card opens its details
 * dialog with full progression, personalities and ability-tree operations. */
const store = useAscensionStore();
defineProps<{ controlsTarget?: HTMLElement | null }>();
const ascensionClient = useAscensionClient();
const PAGE_SIZE = 50;

const selectedTypes = ref<string[]>([]);
const selectedTiers = ref<string[]>([]);
const groupBy = ref<"tier" | "type">("tier");
const configurationExpanded = ref(false);
const search = ref("");
const showUncollected = ref(true);
function toggleFilter(selected: string[], id: string): void {
  const index = selected.indexOf(id);
  if (index < 0) selected.push(id);
  else selected.splice(index, 1);
}
const matches = (name: string, tier: string, types: readonly string[]) =>
  name.toLowerCase().includes(search.value.trim().toLowerCase())
  && (!selectedTiers.value.length || selectedTiers.value.includes(tier))
  && (!selectedTypes.value.length || types.some(id => selectedTypes.value.includes(id)));
const allOwned = computed(() => store.profile?.ascendeds ?? []);
const allNotOwned = computed(() => {
  const ids = new Set(allOwned.value.map((s) => s.ascended_id));
  return (store.catalog?.ascendeds ?? []).filter((s) => !ids.has(s.id));
});
/** Offer every type, including any future catalog types. */
const types = computed(() => [...new Set([...ASCENSION_TYPES.map(type => type.id), ...typesPresent(store.catalog?.ascendeds ?? [])])]);
const catalogById = computed(() => new Map((store.catalog?.ascendeds ?? []).map(info => [info.id, info])));
/** Squad members stay in their own strip. */
const owned = computed(() => allOwned.value.filter(s => !s.in_squad && matches(s.name, s.tier_id, s.ascension_types)));
const notOwned = computed(() => allNotOwned.value.filter(s => matches(s.name, s.start_tier, s.ascension_types)));
function groupCards<T extends { ascension_types: readonly string[] }>(items: T[], tierOf: (item: T) => string) {
  if (groupBy.value === "type") return groupByType(items).map(group => ({ ...group, key: group.typeId ?? "none", tierId: null }));
  const tiers = [...new Set([...(store.catalog?.tiers.map(tier => tier.id) ?? []), ...items.map(tierOf)])];
  return tiers.flatMap(tierId => {
    const members = items.filter(item => tierOf(item) === tierId);
    return members.length ? [{ key: tierId, tierId, typeId: null, label: titleCase(tierId), items: members }] : [];
  });
}
const groups = computed(() => groupCards(owned.value, item => item.tier_id));
const missingGroups = computed(() => groupCards(notOwned.value, item => item.start_tier));
const emptyMessage = computed(() => {
  if (search.value.trim() || selectedTypes.value.length || selectedTiers.value.length) return "No Ascended match your filters.";
  return allOwned.value.length ? "Everyone you collected is in your squad." : "None collected yet.";
});

const openId = ref<string | null>(null);
const detailsOpen = ref(false);
const open = computed(() => store.profile?.ascendeds.find(s => s.ascended_id === openId.value) ?? null);
const squadSlots = computed(() => Array.from({ length: store.profile?.squad_size ?? 0 }, (_, index) => store.squadMembers[index] ?? null));
const battleActive = computed(() => !!store.profile?.active_battle || store.battle?.status === "active");
const squadReason = computed(() => {
  if (battleActive.value) return "Finish your battle first.";
  if (open.value && store.squadIds.includes(open.value.ascended_id)) return "";
  return store.squadIds.length >= (store.profile?.squad_size ?? 0) ? "Squad full. Remove a member first." : "";
});
function toggleSquad(): void {
  if (!open.value || store.busy || squadReason.value) return;
  const id = open.value.ascended_id;
  void (store.squadIds.includes(id) ? store.removeFromSquad(id) : store.addToSquad(id));
}
const detailTab = ref("overview");
const treeVisited = ref(false);
const detailTabs = [{ value: "overview", label: "Overview", icon: "book" as const }, { value: "tree", label: "Ability tree", icon: "tree" as const }, { value: "personalities", label: "Personalities", icon: "ascended" as const }];
const overviewTree = ref<TreeView | null>(null);
const selectedAbility = ref<string | null>(null);
const abilitySelectionRequest = ref(0);
const presetPreview = ref<PersonalityItem[]>([]);
const presetLoading = ref(false);
const presetError = ref("");
const defaultSlot = computed(() => open.value?.default_preset_slot ?? 1);
let previewRequest = 0;
let overviewRequest = 0;
let personalitiesRequest = 0;
async function loadPresetPreview(): Promise<void> {
  const id = openId.value;
  if (!id || !detailsOpen.value) return;
  const request = ++previewRequest;
  presetLoading.value = true;
  presetError.value = "";
  presetPreview.value = [];
  try {
    const preset = await ascensionClient.preset(id, defaultSlot.value);
    if (request !== previewRequest || id !== openId.value) return;
    presetPreview.value = preset.personalities ?? preset.instance_ids.flatMap(key => personalities.value.find(p => p.id === key) ?? []);
  } catch (err) {
    if (request === previewRequest) presetError.value = errorMessage(err);
  } finally { if (request === previewRequest) presetLoading.value = false; }
}
watch([openId, defaultSlot, detailsOpen], () => { if (!detailsOpen.value) ++previewRequest; else void loadPresetPreview(); });
watch(detailTab, tab => { if (tab === "overview") void loadPresetPreview(); });
async function chooseDefault(slot: number): Promise<void> {
  if (open.value && !store.busy) await store.setDefaultPreset(open.value.ascended_id, slot);
}
async function loadOverviewTree(id: string): Promise<void> {
  const request = ++overviewRequest;
  try {
    const result = await ascensionClient.tree(id);
    if (request === overviewRequest && openId.value === id && detailsOpen.value) overviewTree.value = result;
  } catch (err) { if (request === overviewRequest && openId.value === id && detailsOpen.value) detailError.value = errorMessage(err); }
}
function acceptTree(tree: TreeView): void {
  ++overviewRequest;
  overviewTree.value = tree;
}
function closeDetails(): void {
  detailsOpen.value = false;
  ++overviewRequest;
  ++personalitiesRequest;
}
function openAbility(id: string | null): void {
  selectedAbility.value = id;
  ++abilitySelectionRequest.value;
  treeVisited.value = true;
  detailTab.value = "tree";
}
const now = useNowSeconds();
const openInfo = computed(() => store.catalog?.ascendeds.find((s) => s.id === open.value?.ascended_id) ?? null);
/** Seconds until a squad member is ready again; 0 when it is ready. */
const faintOf = (m: OwnedAscended): number => (m.faint_until === null ? 0 : Math.max(0, m.faint_until - now.value));
const faintLeft = computed(() => Math.max(0, (open.value?.faint_until ?? 0) - now.value));
const statsOf = (m: OwnedAscended) => { const info = catalogById.value.get(m.ascended_id); return info ? ascendedStats(info, m.level, store.catalog?.tiers.find(t => t.id === m.tier_id)?.stat_multiplier ?? 1) : undefined; };
const stats = computed(() => open.value ? statsOf(open.value) ?? [] : []);
const personalities = ref<PersonalityItem[]>([]);
const nextCursor = ref<number | null>(null);
const loadingMore = ref(false);
const detailError = ref("");

async function loadPersonalities(cursor: number | null): Promise<void> {
  const request = ++personalitiesRequest;
  const ascended = open.value;
  if (ascended === null) return;
  loadingMore.value = true;
  detailError.value = "";
  try {
    const page = await ascensionClient.personalities(ascended.ascended_id, cursor, PAGE_SIZE);
    if (request !== personalitiesRequest || open.value?.ascended_id !== ascended.ascended_id) return;
    personalities.value = cursor === null ? page.items : [...personalities.value, ...page.items];
    nextCursor.value = page.next_cursor;
  } catch (err) {
    if (request === personalitiesRequest) detailError.value = errorMessage(err);
  } finally {
    if (request === personalitiesRequest) loadingMore.value = false;
  }
}

const upgradeMessage = ref("");
const essences = computed(() => Object.entries(store.profile?.essences ?? {}).filter(([, count]) => count > 0));
const essenceOf = (tierId: string) => store.profile?.essences[tierId] ?? 0;

async function addStar(ascended: OwnedAscended): Promise<void> {
  upgradeMessage.value = "";
  const result = await store.addStar(ascended.ascended_id);
  if (result) {
    upgradeMessage.value = `${ascended.name} gained a star: ${result.stars} of ${result.stars_needed}.`;
  }
}

async function raiseTier(ascended: OwnedAscended): Promise<void> {
  upgradeMessage.value = "";
  const result = await store.raiseTier(ascended.ascended_id);
  if (result) {
    upgradeMessage.value = `${ascended.name} rose to ${titleCase(result.tier_id)}.`;
  }
}

/** Drag and drop (mouse): a collected card dropped on a squad slot joins the squad (replacing
 * that slot's member when the squad is full), a squad card dropped on another slot reorders,
 * and a squad card dropped on the collected list leaves the squad. Click and the buttons stay
 * the way to do it on touch screens. */
const dragId = ref<string | null>(null);
const dragFromSquad = ref(false);
const overSlot = ref<number | null>(null);
const overCollected = ref(false);
function dragStart(event: DragEvent, id: string, fromSquad: boolean): void {
  if (store.busy || battleActive.value) { event.preventDefault(); return; }
  dragId.value = id;
  dragFromSquad.value = fromSquad;
  if (event.dataTransfer) { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", id); }
}
function dragEnd(): void {
  dragId.value = null;
  overSlot.value = null;
  overCollected.value = false;
}
function dragOverSlot(event: DragEvent, index: number): void {
  if (dragId.value === null) return;
  event.preventDefault();
  overSlot.value = index;
}
function dragOverCollected(event: DragEvent): void {
  if (dragId.value === null || !dragFromSquad.value) return;
  event.preventDefault();
  overCollected.value = true;
}
async function dropOnSlot(index: number): Promise<void> {
  const id = dragId.value;
  dragEnd();
  if (id === null || store.busy || battleActive.value) return;
  const ids = [...store.squadIds];
  const current = ids.indexOf(id);
  if (current >= 0) {
    ids.splice(current, 1);
    ids.splice(Math.min(index, ids.length), 0, id);
    if (ids.every((value, i) => value === store.squadIds[i])) return;
  } else if (ids.length >= (store.profile?.squad_size ?? 0)) {
    if (index >= ids.length) return;
    ids[index] = id;
  } else {
    ids.splice(Math.min(index, ids.length), 0, id);
  }
  await store.setSquad(ids);
}
async function dropOnCollected(): Promise<void> {
  const id = dragId.value;
  const fromSquad = dragFromSquad.value;
  dragEnd();
  if (id === null || !fromSquad || store.busy || battleActive.value) return;
  await store.removeFromSquad(id);
}

function show(ascended: OwnedAscended): void {
  detailTab.value = "overview";
  treeVisited.value = false;
  upgradeMessage.value = "";
  openId.value = ascended.ascended_id;
  detailsOpen.value = true;
  personalities.value = [];
  nextCursor.value = null;
  overviewTree.value = null;
  selectedAbility.value = null;
  void loadOverviewTree(ascended.ascended_id);
  void loadPersonalities(null);
}
</script>

<template>
  <section class="collection">
    <aside class="filter-rail" :class="{ expanded: configurationExpanded }" aria-label="Collection filters">
      <button type="button" class="configuration-toggle" :aria-expanded="configurationExpanded" aria-controls="collection-configuration" @click="configurationExpanded = !configurationExpanded">
        <EmIcon name="settings" />Configuration<EmIcon class="configuration-arrow" name="arrow" />
      </button>
      <div id="collection-configuration" class="configuration-content">
        <label class="filter-label">Search<input v-model="search" type="search" placeholder="Find an Ascended" aria-label="Search collection" /></label>
        <fieldset class="filter-group type-filters">
          <legend>Ascension Type</legend>
          <div class="chips">
            <button v-for="id in types" :key="id" type="button" class="chip" :data-type-filter="id" :aria-pressed="selectedTypes.includes(id)" @click="toggleFilter(selectedTypes, id)">
              <TypeSymbol :type-id="id" :size="20" decorative />{{ typeLabel(id) }}
            </button>
          </div>
        </fieldset>
        <fieldset class="filter-group tier-filters">
          <legend>Tier</legend>
          <div class="chips">
            <button v-for="tier in store.catalog?.tiers" :key="tier.id" type="button" class="chip" :data-tier-filter="tier.id" :aria-pressed="selectedTiers.includes(tier.id)" @click="toggleFilter(selectedTiers, tier.id)">
              <EmTierBadge :tier-id="tier.id" />
            </button>
          </div>
        </fieldset>
        <fieldset class="filter-group grouping-filters">
          <legend>Group by</legend>
          <label><input v-model="groupBy" type="radio" name="collection-grouping" value="tier" />Tier</label>
          <label><input v-model="groupBy" type="radio" name="collection-grouping" value="type" />Ascension Type</label>
        </fieldset>
        <label class="uncollected"><input v-model="showUncollected" type="checkbox" aria-label="Show uncollected" />Show uncollected</label>
      </div>
      <p class="rail-count em-num">{{ allOwned.length }}/{{ store.catalog?.ascendeds.length ?? 0 }} Acquired</p>
    </aside>
    <main class="collection-main">
    <ul v-if="essences.length" class="essences" aria-label="Essence">
      <li v-for="[tierId, count] in essences" :key="tierId" :style="{ '--tier': `var(--em-tier-${tierId}, var(--em-tier-common))` }">
        <EmEssence :tier-id="tierId" /><span class="essence-name">{{ titleCase(tierId) }} essence</span> <strong class="em-num">{{ count }}</strong>
      </li>
    </ul>
    <section class="squad-section" aria-label="Squad">
      <h3 class="em-pixel">Your squad <small class="em-num">{{ store.squadIds.length }} / {{ store.profile?.squad_size }}</small>
        <span class="squad-help">
          <button type="button" class="help-icon" aria-label="About your squad" aria-describedby="squad-help-tip"><EmIcon name="info" :size="18" /></button>
          <span id="squad-help-tip" role="tooltip" class="help-tip">
            <strong>Your squad</strong>
            Your squad is who can fight in battle. You pick one ready member for each fight, and the rest share a smaller XP reward. With an empty squad you cannot battle.
            <strong>Add</strong>
            Drag an Ascended from Collected onto a squad slot, or open its details and choose Add to squad.
            <strong>Remove</strong>
            Drag a member out of the squad back to Collected, or open its details and choose Remove from squad.
          </span>
        </span></h3>
      <ul class="squad-strip">
        <li v-for="(member, index) in squadSlots" :key="index" class="squad-slot" :class="{ 'squad-empty': !member, 'drop-over': dragId !== null && overSlot === index }" @dragover="dragOverSlot($event, index)" @dragleave="overSlot = null" @drop.prevent="dropOnSlot(index)">
          <template v-if="member">
            <div
              v-if="store.catalog?.ascendeds.find(a => a.id === member.ascended_id)"
              class="squad-card"
              :class="{ down: faintOf(member) > 0 }"
              :style="{ '--tier': `var(--em-tier-${member.tier_id}, var(--em-tier-common))` }"
              role="button"
              tabindex="0"
              draggable="true"
              :aria-label="`${member.name}, details`"
              @dragstart="dragStart($event, member.ascended_id, true)"
              @dragend="dragEnd"
              @click="show(member)"
              @keydown.enter.prevent="show(member)"
              @keydown.space.prevent="show(member)"
            >
              <AscendedPreviewCard class="squad-face preview-lift" :ascended="catalogById.get(member.ascended_id)!" :level="member.level" :tier-id="member.tier_id" :stars="member.stars" :stats="statsOf(member)" show-level />
              <span v-if="faintOf(member) > 0" class="squad-fainted"><EmIcon name="clock" :size="14" /> Fainted · <strong class="em-num">{{ formatCountdown(faintOf(member)) }}</strong></span>
            </div>
          </template>
          <span v-else>Empty slot</span>
        </li>
      </ul>
      <p v-if="battleActive" class="muted">Finish your battle first.</p>
    </section>

    <div class="collected-zone" :class="{ 'drop-over': overCollected }" @dragover="dragOverCollected" @dragleave="overCollected = false" @drop.prevent="dropOnCollected">
      <div class="section-head">
        <h3 class="em-pixel">Collected <small class="em-num">{{ owned.length }}</small></h3>
        <small>Press a card for details</small>
      </div>
        <section v-for="group in groups" :key="group.key" class="group" :data-type="group.typeId ?? undefined" :data-tier="group.tierId ?? undefined">
          <h4 class="group-name"><TypeSymbol v-if="group.typeId" :type-id="group.typeId" :size="40" decorative />{{ group.label }} <small class="em-num">{{ group.items.length }}</small></h4>
          <div class="grid">
            <div v-for="ascended in group.items" :key="ascended.ascended_id" class="owned-entry" draggable="true" @dragstart="dragStart($event, ascended.ascended_id, false)" @dragend="dragEnd">
              <AscendedCard :ascended="ascended" :selected="openId === ascended.ascended_id" @open="show(ascended)" />
            </div>
          </div>
        </section>

      <p v-if="owned.length === 0" class="empty">{{ emptyMessage }}</p>

    </div>

    <template v-if="showUncollected && notOwned.length">
      <div class="section-head">
        <h3 class="em-pixel">Not collected yet</h3>
        <small>{{ notOwned.length }} still to find</small>
      </div>
      <section v-for="group in missingGroups" :key="group.key" class="missing-group" :data-type="group.typeId ?? undefined" :data-tier="group.tierId ?? undefined">
        <h4 class="group-name"><TypeSymbol v-if="group.typeId" :type-id="group.typeId" :size="40" decorative />{{ group.label }} <small class="em-num">{{ group.items.length }}</small></h4>
        <ul class="grid missing">
          <li v-for="ascended in group.items" :key="ascended.id" class="missing-ascended">
            <AscendedPreviewCard class="back preview-lift" :ascended="ascended" :tier-id="ascended.start_tier" flipped />
          </li>
        </ul>
      </section>
    </template>

    </main>
    <EmDialog class="ascended-details" :open="detailsOpen && open !== null" :title="open?.name ?? 'Ascended details'" wide @close="closeDetails">
      <template #header-actions><EmTabs v-model="detailTab" :options="detailTabs" ariaLabel="Ascended detail sections" @update:model-value="value => { if (value === 'tree') treeVisited = true; }" /></template>
      <div v-if="open && detailsOpen" class="details" :class="{ 'tree-expanded': detailTab !== 'overview' }">
        <div class="detail-meta"><span class="copy-summary"><strong>{{ open.copies }}</strong> {{ open.copies === 1 ? 'spare copy' : 'spare copies' }}</span><span class="battle-status" :class="{ fainted: faintLeft > 0 }">{{ faintLeft > 0 ? 'Fainted, ready in ' + formatCountdown(faintLeft) : 'Ready for battle' }}</span></div>
        <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>
        <section v-if="detailTab === 'overview'" class="overview" role="tabpanel" aria-label="Overview">
          <img v-if="openInfo?.art.main_card" class="detail-portrait" :src="openInfo.art.main_card" :alt="open.name" />
          <div class="overview-shade" />
          <aside class="summary">
            <p class="level"><EmIcon name="ascended" /> <strong>{{ open.stars }}</strong> stars</p>
            <p class="level"><EmIcon name="shield" /> Level {{ open.level }} / {{ open.level_cap }}</p>
            <div class="xp"><template v-if="open.xp_needed !== null"><span class="em-num">{{ open.xp }} / {{ open.xp_needed }} XP</span><EmBar :value="open.xp" :max="open.xp_needed" :label="open.name + ' XP'" /></template><span v-else>Highest level reached</span></div>
            <EmTierBadge :tier-id="open.tier_id" />
            <dl class="current-stats" aria-label="Current stats"><div v-for="stat in stats" :key="stat.key"><dt><EmIcon :name="stat.key === 'hp' ? 'heart' : stat.key === 'speed' ? 'feather' : 'flame'" />{{ stat.label }}</dt><dd class="em-num">{{ stat.value }}</dd></div></dl>
            <div class="badges"><span v-for="id in open.ascension_types" :key="id" class="type-chip"><TypeSymbol :type-id="id" :size="22" decorative />{{ typeLabel(id) }}</span></div>
            <div class="squad-control"><EmButton :disabled="!!squadReason || store.busy" :aria-busy="store.busy" @click="toggleSquad">{{ store.busy ? 'Saving squad…' : store.squadIds.includes(open.ascended_id) ? 'Remove from squad' : 'Add to squad' }}</EmButton><p v-if="squadReason" class="muted">{{ squadReason }}</p></div>
            <details class="progression-drawer"><summary>Progression & abilities</summary>
        <aside class="progression-panel" aria-label="Progression"><h3 class="em-pixel">Progression</h3><div class="progression-resources"><div><small>Spare copies</small><strong class="em-num">{{ open.copies }}</strong></div><div><small class="essence-label"><EmEssence :tier-id="open.tier_id" />{{ titleCase(open.tier_id) }} essence</small><strong class="em-num">{{ essenceOf(open.tier_id) }}</strong></div></div><h4 class="em-pixel">Star progression</h4>
          <div class="upgrade">
            <template v-if="open.stars_needed !== null">
              <EmBar :value="open.stars" :max="open.stars_needed" :label="`${open.name} stars`" />
              <span class="em-num">Stars {{ open.stars }} / {{ open.stars_needed }}<template v-if="open.next_tier_id"> to reach {{ titleCase(open.next_tier_id) }}</template></span>
              <h5 class="cost-head">A star costs</h5>
              <ul class="star-cost">
                <li :class="{ met: open.copies >= 1 }"><span>1 spare copy</span><small class="em-num">You have {{ open.copies }}</small></li>
                <li :class="{ met: essenceOf(open.tier_id) >= open.star_essence_cost }"><span class="essence-label"><EmEssence :tier-id="open.tier_id" />{{ open.star_essence_cost }} {{ titleCase(open.tier_id) }} essence</span><small class="em-num">You have {{ essenceOf(open.tier_id) }}</small></li>
              </ul>
              <div class="upgrade-actions">
                <EmButton v-if="open.can_tier_up" variant="primary" :disabled="store.busy" @click="raiseTier(open)">
                  Raise to {{ titleCase(open.next_tier_id ?? "") }}
                </EmButton>
                <span v-else-if="open.stars >= open.stars_needed">Maximum stars reached</span>
                <EmButton v-else variant="primary" :disabled="!open.can_star_up || store.busy" @click="addStar(open)">Add a star</EmButton>
              </div>
            </template>
            <span v-else>Top of its ladder: no more stars.</span>
            <p v-if="upgradeMessage" class="upgrade-note" role="status">{{ upgradeMessage }}</p>
          </div>

        </aside>

            <div v-if="openInfo" class="overview-effects"><h4>Innate passive</h4><strong>{{ titleCase(openInfo.passive.kind) }}</strong><p>{{ passiveText(openInfo.passive.kind, openInfo.passive.params) }}</p><h4>Foundation abilities</h4><article v-for="ability in openInfo.abilities" :key="ability.id"><strong>{{ ability.name }}</strong><p>{{ abilityEffect(ability) }} · Level {{ ability.unlock_level }}</p></article></div>
            </details>
          </aside>
          <div class="overview-loadout"><h4>Equipped abilities</h4><AbilitySlots :tree="overviewTree" :ascended-id="open.ascended_id" @select="openAbility" /></div>
          <aside class="overview-presets" aria-label="Battle default preset">
            <div class="preset-preview"><h4>Preset {{ defaultSlot }}</h4><span class="default-badge">★ Battle default</span><p class="muted">Used when battle begins</p><p v-if="presetLoading" role="status">Loading preset…</p><EmNotice v-else-if="presetError" tone="error">{{ presetError }}</EmNotice><ul v-else><li v-for="index in 3" :key="index"><EmIcon name="ascended" /><span>{{ presetPreview[index - 1] ? titleCase(presetPreview[index - 1]!.type) : 'Empty personality slot' }}</span></li></ul><button class="edit-personalities" type="button" @click="detailTab = 'personalities'">Edit personalities <EmIcon name="arrow" :size="14" /></button></div>
            <div class="default-slots"><button v-for="slot in 5" :key="slot" type="button" :class="{ active: defaultSlot === slot }" :aria-label="'Use preset ' + slot + ' as battle default'" :aria-pressed="defaultSlot === slot" :disabled="store.busy" @click="chooseDefault(slot)">{{ slot }}<small v-if="defaultSlot === slot">★</small></button></div>
          </aside>
          <EmNotice v-if="detailError" class="overview-error" tone="error">{{ detailError }}</EmNotice>
        </section>
        <section v-show="detailTab === 'personalities'" class="personality-tab" role="tabpanel" aria-label="Personalities">
          <div class="people-head"><h4>Personalities</h4><small>{{ personalities.length }}{{ nextCursor !== null ? '+' : '' }} collected</small></div>
          <EmNotice v-if="detailError" tone="error">{{ detailError }}</EmNotice><p v-if="loadingMore" class="muted" role="status">Loading personalities…</p>
          <PresetEditor :key="open.ascended_id" :ascended-id="open.ascended_id" :ascended-name="open.name" :personalities="personalities" :default-slot="defaultSlot" @saved="loadPresetPreview" />
          <button v-if="nextCursor !== null" type="button" class="more" :disabled="loadingMore" @click="loadPersonalities(nextCursor)">Show more</button>
        </section>
        <section v-if="treeVisited" v-show="detailTab === 'tree'" class="ability-tree-panel" role="tabpanel" aria-label="Ability tree"><TreeTab :key="open.ascended_id" :ascended="open" :initial-selected-id="selectedAbility" :selection-request="abilitySelectionRequest" @loaded="acceptTree" /></section>
      </div>
    </EmDialog>
  </section>
</template>

<style scoped>
.collection { display: grid; grid-template-columns: 184px minmax(0, 1fr); gap: 18px; align-items: start; }
.summary, .progression-panel, .stats-panel, .overview-effects { border: 1px solid var(--em-border); background: linear-gradient(135deg, var(--em-panel), var(--em-bg)); box-shadow: inset 0 0 0 3px rgb(255 255 255 / 2%); }
.filter-rail { padding: 16px 12px; display: flex; flex-direction: column; gap: 18px; position: sticky; top: 18px; }
.filter-rail h3 { font-size: 14px; margin: 0; }
.filter-label { display: flex; flex-direction: column; gap: 8px; color: var(--em-muted); font-size: 12px; }
.filter-label input, .filter-label select { min-height: 40px; width: 100%; box-sizing: border-box; border: 1px solid var(--em-border); color: var(--em-text); background: var(--em-bg); padding: 8px; font: inherit; }
.filters { display: flex; flex-direction: column; gap: 16px; }
.chips { display: flex; flex-direction: column; gap: 6px; }
.chip { display: flex; align-items: center; gap: 8px; min-height: 40px; border: 1px solid transparent; padding: 6px 10px; color: var(--em-muted); background: transparent; font: inherit; font-size: 13px; text-align: left; cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--em-accent); border-left: 4px solid var(--em-accent); color: var(--em-text); background: color-mix(in srgb, var(--em-accent) 20%, var(--em-panel)); }
.uncollected { display: flex; align-items: center; gap: 8px; font-size: 12px; min-height: 40px; }
.uncollected input { accent-color: var(--em-accent); width: 18px; height: 18px; }
.rail-count { margin: 0; padding-top: 12px; border-top: 1px solid var(--em-divider); font-size: 12px; color: var(--em-muted); }
.collection-main { min-width: 0; }
.squad-section h3 { margin: 0 0 12px; font-size: 15px; }
h3 small { color: var(--em-muted); font-size: 12px; margin-left: 12px; }
.squad-strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(136px, 1fr)); gap: 10px; padding: 0; margin: 0; list-style: none; }
.squad-slot { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.squad-card { cursor: pointer; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.squad-face { --card-width: 100%; }
.squad-card.down .squad-face { filter: grayscale(1); opacity: 0.72; }
.squad-fainted { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--em-danger); }
.squad-section h3 { display: flex; align-items: center; gap: 8px; }
.squad-help { position: relative; display: inline-flex; }
.help-icon { display: inline-flex; padding: 2px; border: 0; background: none; color: var(--em-muted); cursor: help; }
.help-icon:hover, .help-icon:focus-visible { color: var(--em-accent); }
.help-tip { position: absolute; left: 0; top: calc(100% + 8px); z-index: 30; display: none; flex-direction: column; gap: 4px; width: 300px; padding: 12px; border: 1px solid var(--em-accent); background: var(--em-header); box-shadow: 0 8px 24px #000a; color: var(--em-text); font: 12px/1.5 var(--em-font-body); text-transform: none; letter-spacing: 0; }
.help-tip strong { color: var(--em-accent); font-size: 11px; text-transform: uppercase; margin-top: 4px; }
.help-tip strong:first-child { margin-top: 0; }
.squad-help:hover .help-tip, .squad-help:focus-within .help-tip { display: flex; }
.squad-slot :deep(.em-btn) { min-height: 30px; font-size: 11px; padding: 3px 8px; }
.squad-empty { min-height: 142px; border: 1px dashed var(--em-border); padding: 6px; justify-content: center; align-items: center; color: var(--em-muted); font-size: 12px; }
.drop-over { outline: 2px dashed var(--em-accent); outline-offset: 4px; }
.section-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin: 22px 0 12px; }
.section-head h3 { margin: 0; font-size: 15px; }
.section-head small { color: var(--em-muted); font-size: 11px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(136px, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
.owned-entry { min-width: 0; }
.empty { color: var(--em-muted); font-size: 13px; padding-block: 12px; }
.missing-ascended { min-width: 0; }
.back { --card-width: 100%; opacity: .6; }
.essences { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 14px; padding: 0; list-style: none; }
.essences li { display: flex; gap: 6px; align-items: center; font-size: 12px; }
.essence-name { color: var(--tier); font-weight: 600; white-space: nowrap; }
.essence-label { display: inline-flex; gap: 6px; align-items: center; }
.group { margin-bottom: 18px; }
.group-name { display: flex; align-items: center; gap: 8px; margin: 0 0 10px; font-size: 14px; }
.group-name small { color: var(--em-muted); }
.collection :deep(.em-dialog.ascended-details) { width: min(1440px, calc(100vw - 32px)); box-sizing: border-box; padding: 20px; }
.details { display: grid; grid-template-columns: 218px minmax(0, 1fr) 280px; gap: 16px; align-items: stretch; height: min(820px, calc(100dvh - 150px)); }
.details.tree-expanded .side { grid-column: 2 / -1; }
.details > * { min-height: 0; overflow-y: auto; }
.summary { display: flex; flex-direction: column; gap: 12px; padding: 12px; min-width: 0; }
.detail-portrait { width: 100%; height: 260px; object-fit: contain; image-rendering: pixelated; background: #060d15; border: 1px solid var(--em-border); }
.name { margin: 0; font-size: 17px; }
.level { color: var(--em-muted); margin: 0; font-size: 13px; }
.copy-summary { padding-block: 12px; border-block: 1px solid var(--em-divider); font-size: 13px; }
.copy-summary strong { margin-right: 4px; font-size: 22px; }
.copy-summary small { display: block; color: var(--em-muted); font-size: 11px; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.type-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--em-muted); }
.current-stats { display: flex; justify-content: space-between; margin: 0; gap: 12px; padding: 12px 0; border-block: 1px solid var(--em-divider); }
.current-stats dt { color: var(--em-muted); font-size: 11px; }
.current-stats dd { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.battle-status { color: var(--em-success); font-size: 12px; margin: 0; }
.battle-status.fainted { color: var(--em-danger); }
.side { display: flex; min-width: 0; flex-direction: column; gap: 14px; }
.overview { display: flex; flex-direction: column; gap: 12px; }
.stats-panel, .overview-effects { padding: 14px; }
.stats-panel h4, .overview-effects h4 { margin: 0 0 12px; font-size: 13px; }
.overview-effects { display: flex; flex-direction: column; gap: 10px; }
.overview-effects h4 { color: var(--em-accent); margin: 8px 0 0; }
.overview-effects p { color: var(--em-muted); font-size: 12px; margin: 0; }
.overview-effects article { padding: 10px; border: 1px solid var(--em-border); background: var(--em-bg); }
.overview-effects article strong { display: block; margin-bottom: 4px; }
.squad-control { display: flex; flex-direction: column; gap: 8px; }
.squad-control .muted { font-size: 12px; margin: 0; }
.progression-panel { padding: 14px; display: flex; flex-direction: column; gap: 14px; }
.progression-panel h3, .progression-panel h4 { font-size: 13px; margin: 0; }
.progression-resources { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.progression-resources > div { display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--em-border); background: var(--em-bg); }
.progression-resources small { color: var(--em-muted); font-size: 10px; text-transform: uppercase; }
.progression-resources strong { font-size: 24px; }
.upgrade, .xp { display: flex; flex-direction: column; gap: 10px; margin: 0; font-size: 12px; color: var(--em-muted); }
.xp { margin-top: 12px; }
.cost-head { margin: 0; font-size: 12px; color: var(--em-muted); }
.star-cost { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; }
.star-cost li { display: flex; justify-content: space-between; gap: 8px; padding: 8px 10px; border: 1px solid var(--em-border); background: var(--em-bg); color: var(--em-text); }
.star-cost li.met { border-color: var(--em-success); }
.star-cost small { color: var(--em-muted); }
.upgrade-actions :deep(.em-btn) { width: 100%; }
.upgrade-note { color: var(--em-text); }
.people-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.people-head h4 { margin: 0; font-size: 15px; }
.people-head small { color: var(--em-muted); font-size: 12px; }
.more { min-height: 44px; color: var(--em-accent); background: transparent; border: 0; font: inherit; cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible, .squad-card:focus-visible { outline: 2px solid var(--em-accent); outline-offset: 3px; }
@media (max-width: 1180px) { .collection { grid-template-columns: 160px minmax(0, 1fr); gap: 12px; } .details { grid-template-columns: 180px minmax(0, 1fr); } .progression-panel { grid-column: 2; } }
@media (max-width: 900px) { .details { height: auto; } .details.tree-expanded .side { grid-column: 1; } .details > * { overflow-y: visible; } .collection { grid-template-columns: 150px minmax(0, 1fr); } .details.tree-expanded { grid-template-columns: minmax(0, 1fr); } .tree-expanded .summary { display: grid; grid-template-columns: 100px minmax(0, 1fr); align-items: start; } .tree-expanded .summary .detail-portrait { grid-row: 1 / span 4; height: 150px; } .tree-expanded .summary .battle-status, .tree-expanded .summary .squad-control { grid-column: 1 / -1; } }
@media (max-width: 600px) { .collection { grid-template-columns: minmax(0, 1fr); } .filter-rail { position: static; gap: 12px; } .chips { flex-direction: row; flex-wrap: wrap; } .filters { gap: 12px; } .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .squad-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .squad-empty { min-height: 90px; } .details { grid-template-columns: minmax(0, 1fr); } .summary { display: grid; grid-template-columns: 100px minmax(0, 1fr); } .summary .detail-portrait { grid-row: span 4; height: 150px; } .summary .battle-status { grid-column: 1 / -1; } .progression-panel { grid-column: 1; } .collection :deep(.em-dialog.ascended-details) { padding: 14px; } }

.collection {grid-template-columns:200px minmax(0,1fr);gap:12px;}
.summary,.progression-panel,.stats-panel,.overview-effects {border-radius:var(--em-radius);background:linear-gradient(125deg,#102735,#091c29);}
.filter-rail {padding:8px 12px 14px;gap:14px;}.filter-rail h3{font-size:11px;color:var(--em-muted);}
.all-filter{padding:10px 12px;color:var(--em-text);background:linear-gradient(#193243,#102737);border:1px solid var(--em-border);border-left:4px solid var(--em-accent);border-radius:var(--em-radius);font:inherit;font-size:13px;text-align:left;cursor:pointer;}
.filter-label input,.filter-label select {border-radius:var(--em-radius);background:linear-gradient(#193243,#0e2231);}
.squad-strip,.grid {grid-template-columns:repeat(auto-fill,136px);justify-content:start;}
.squad-card,.squad-slot,.owned-entry,.missing-ascended{width:136px;}
.squad-empty{box-sizing:border-box;}
.current-stats dd {font-size:21px;}.progression-resources>div,.star-cost li,.overview-effects article {background:#102735;border-radius:var(--em-radius);}
.side :deep(.tab){border:1px solid var(--em-border);border-radius:var(--em-radius);background:linear-gradient(#112b3b,#0a1c28);}
.side :deep(.tab.active),:deep(.em-button.primary:not(:disabled)){background:linear-gradient(#fac88a,#de9655);border-color:#f5b56f;color:#15222e;box-shadow:inset 0 1px #ffdeb0;}
@media(max-width:1180px){.collection{grid-template-columns:170px minmax(0,1fr);}}
@media(max-width:600px){.collection{grid-template-columns:minmax(0,1fr);}}
.filter-rail { padding:8px 0; border:0; border-radius:0; background:transparent; box-shadow:none; }
.configuration-content { display:flex; flex-direction:column; gap:18px; }
.configuration-toggle { display:none; }
.filter-group { display:flex; flex-direction:column; gap:8px; min-width:0; border:0; padding:0; margin:0; }
.filter-group legend { padding:0; margin-bottom:8px; color:var(--em-muted); font-size:12px; }
.grouping-filters label { display:flex; align-items:center; gap:8px; min-height:32px; font-size:12px; }
.grouping-filters input { accent-color:var(--em-accent); }
.rail-count { border:0; padding-top:0; }
.missing-group { margin-bottom:18px; }
@media (orientation:landscape) {
  .collection { grid-template-columns:200px minmax(0,1fr); }
  .filter-rail { position:static; }
}
@media (orientation:portrait) {
  .collection { grid-template-columns:minmax(0,1fr); }
  .filter-rail { position:static; gap:12px; }
  .configuration-toggle { display:flex; align-items:center; gap:8px; width:100%; min-height:44px; padding:8px 0; border:0; background:transparent; color:var(--em-text); font:inherit; cursor:pointer; }
  .configuration-arrow { margin-left:auto; transform:rotate(90deg); }
  .expanded .configuration-arrow { transform:rotate(-90deg); }
  .configuration-content { display:none; }
  .expanded .configuration-content { display:flex; }
  .chips { flex-direction:row; flex-wrap:wrap; }
}
</style>
<style scoped src="./ascendedDetails.css" />
