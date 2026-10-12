<script setup lang="ts">
import { computed, ref } from "vue";
import { useAscensionClient, type OwnedAscended, type PersonalityItem } from "../api/AscensionClient";
import cardBackUrl from "../assets/card_back.png";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { filterByType, groupByType, typeLabel, typesPresent } from "../utils/ascensionTypes";
import { formatCountdown, titleCase, passiveText, abilityEffect } from "../utils/ascension";
import { spriteFor, spriteFocus } from "../utils/sprites";
import { useNowSeconds } from "../composables/useNowSeconds";
import TreeTab from "./TreeTab.vue";
import PresetEditor from "./PresetEditor.vue";
import AscendedCard from "./AscendedCard.vue";
import AscendedTemplateCard from "./AscendedTemplateCard.vue";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmBar from "./ui/EmBar.vue";
import EmButton from "./ui/EmButton.vue";
import EmDialog from "./ui/EmDialog.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmSwitch from "./ui/EmSwitch.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";
import EmTabs from "./ui/EmTabs.vue";
import TypeSymbol from "./ui/TypeSymbol.vue";

/** The Collection tab: owned Ascended as small cards with a caption, the rest of the
 * catalog as face-down cards, and a card's details (the full card, personalities,
 * presets) in a dialog. */
const store = useAscensionStore();
defineProps<{ controlsTarget?: HTMLElement | null }>();
const ascensionClient = useAscensionClient();
const PAGE_SIZE = 50;

const typeFilter = ref<string | null>(null);
const grouped = ref(false);
const allOwned = computed(() => store.profile?.ascendeds ?? []);
const allNotOwned = computed(() => {
  const ids = new Set(allOwned.value.map((s) => s.ascended_id));
  return (store.catalog?.ascendeds ?? []).filter((s) => !ids.has(s.id));
});
/** The types to offer as filters: those any Ascended in the catalog has. */
const types = computed(() => typesPresent(store.catalog?.ascendeds ?? []));
const owned = computed(() => filterByType(allOwned.value, typeFilter.value));
const notOwned = computed(() => filterByType(allNotOwned.value, typeFilter.value));
const groups = computed(() => groupByType(owned.value));

const openId = ref<string | null>(null);
const open = computed(() => store.profile?.ascendeds.find(s => s.ascended_id === openId.value) ?? null);
const squadSlots = computed(() => Array.from({ length: store.profile?.squad_size ?? 0 }, (_, index) => store.squadMembers[index] ?? null));
const battleActive = computed(() => !!store.profile?.active_battle || store.battle?.status === "active");
const squadReason = computed(() => {
  if (battleActive.value) return "Finish your battle first.";
  if (open.value && store.squadIds.includes(open.value.ascended_id)) {
    return store.squadIds.length <= 1 ? "Keep at least one Ascended." : "";
  }
  return store.squadIds.length >= (store.profile?.squad_size ?? 0) ? "Squad full. Remove a member first." : "";
});
function toggleSquad(): void {
  if (!open.value || store.busy || squadReason.value) return;
  const id = open.value.ascended_id;
  void (store.squadIds.includes(id) ? store.removeFromSquad(id) : store.addToSquad(id));
}
const detailTab = ref("overview");
const treeVisited = ref(false);
const detailTabs = [{ value: "overview", label: "Overview" }, { value: "personalities", label: "Personalities" }, { value: "tree", label: "Ability tree" }];
const now = useNowSeconds();
const openInfo = computed(() => store.catalog?.ascendeds.find((s) => s.id === open.value?.ascended_id) ?? null);
const faintLeft = computed(() => Math.max(0, (open.value?.faint_until ?? 0) - now.value));
const stats = computed(() => {
  const info = openInfo.value;
  const owned = open.value;
  if (!info || !owned) return [];
  const multiplier = store.catalog?.tiers.find(t => t.id === owned.tier_id)?.stat_multiplier ?? 1;
  return ["hp", "power", "speed"].map(key => ({ key, value: Math.max(1, Math.floor(((info.base[key] ?? 0) + (info.growth[key] ?? 0) * (owned.level - 1)) * multiplier + 1e-9)) }));
});
const personalities = ref<PersonalityItem[]>([]);
const nextCursor = ref<number | null>(null);
const loadingMore = ref(false);
const detailError = ref("");

async function loadPersonalities(cursor: number | null): Promise<void> {
  const ascended = open.value;
  if (ascended === null) return;
  loadingMore.value = true;
  detailError.value = "";
  try {
    const page = await ascensionClient.personalities(ascended.ascended_id, cursor, PAGE_SIZE);
    if (open.value?.ascended_id !== ascended.ascended_id) return;
    personalities.value = cursor === null ? page.items : [...personalities.value, ...page.items];
    nextCursor.value = page.next_cursor;
  } catch (err) {
    detailError.value = errorMessage(err);
  } finally {
    loadingMore.value = false;
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

function show(ascended: OwnedAscended): void {
  detailTab.value = "overview";
  treeVisited.value = false;
  upgradeMessage.value = "";
  openId.value = ascended.ascended_id;
  personalities.value = [];
  nextCursor.value = null;
  void loadPersonalities(null);
}
</script>

<template>
  <section class="collection">
    <Teleport :to="controlsTarget ?? 'body'" :disabled="!controlsTarget">
    <div v-if="types.length" class="filters">
      <div class="chips" role="group" aria-label="Filter by Ascension Type">
        <button type="button" class="chip" :aria-pressed="typeFilter === null" @click="typeFilter = null">All</button>
        <button
          v-for="id in types"
          :key="id"
          type="button"
          class="chip"
          :aria-pressed="typeFilter === id"
          @click="typeFilter = typeFilter === id ? null : id"
        >
          <TypeSymbol :type-id="id" :size="20" decorative />{{ typeLabel(id) }}
        </button>
      </div>
      <EmSwitch v-model="grouped" label="Group by type" />
    </div>

    </Teleport>
    <section class="squad-section" aria-label="Squad">
      <h3 class="em-pixel">Squad</h3>
      <ul class="squad-strip">
        <li v-for="(member, index) in squadSlots" :key="index" class="squad-slot" :class="{ 'squad-empty': !member }">
          <template v-if="member">
            <AscendedPreviewCard v-if="store.catalog?.ascendeds.find(a => a.id === member.ascended_id)" :ascended="store.catalog!.ascendeds.find(a => a.id === member.ascended_id)!" :level="member.level" :tier-id="member.tier_id" show-level />
            <EmButton :disabled="store.squadIds.length <= 1 || battleActive || store.busy" :aria-label="`Remove ${member.name} from squad`" :aria-busy="store.busy" @click="store.removeFromSquad(member.ascended_id)">Remove</EmButton>
          </template>
          <span v-else>Empty slot</span>
        </li>
      </ul>
      <p v-if="battleActive" class="muted">Finish your battle first.</p>
    </section>
    <ul v-if="essences.length" class="essences" aria-label="Essence">
      <li v-for="[tierId, count] in essences" :key="tierId" :style="{ '--tier': `var(--em-tier-${tierId}, var(--em-tier-common))` }">
        <EmTierBadge :tier-id="tierId" :label="`${titleCase(tierId)} essence`" /> <strong class="em-num">{{ count }}</strong>
      </li>
    </ul>

    <div class="section-head">
      <h3 class="em-pixel">Collected Ascended</h3>
      <small>Choose a card to manage presets</small>
    </div>
    <template v-if="grouped">
      <section v-for="group in groups" :key="group.typeId ?? 'none'" class="group" :data-type="group.typeId ?? 'none'">
        <h4 class="group-name"><TypeSymbol v-if="group.typeId" :type-id="group.typeId" :size="40" decorative />{{ group.label }} <small class="em-num">{{ group.items.length }}</small></h4>
        <div class="grid">
          <div v-for="ascended in group.items" :key="ascended.ascended_id" class="owned-entry">
            <AscendedCard :ascended="ascended" @open="show(ascended)" />
            <span v-if="ascended.in_squad" class="squad-marker">Squad</span>
          </div>
        </div>
      </section>
    </template>
    <div v-else class="grid">
      <div v-for="ascended in owned" :key="ascended.ascended_id" class="owned-entry">
        <AscendedCard :ascended="ascended" @open="show(ascended)" />
        <span v-if="ascended.in_squad" class="squad-marker">Squad</span>
      </div>
    </div>
    <p v-if="owned.length === 0" class="empty">{{ typeFilter === null ? "None collected yet." : `No ${typeLabel(typeFilter)} Ascended collected yet.` }}</p>

    <template v-if="notOwned.length">
      <div class="section-head">
        <h3 class="em-pixel">Not collected yet</h3>
        <small>{{ notOwned.length }} still to find</small>
      </div>
      <ul class="grid missing">
        <li v-for="ascended in notOwned" :key="ascended.id" class="missing-ascended em-lift" :style="{ '--tier': 'var(--em-border)' }">
          <img class="back" :src="cardBackUrl" alt="" draggable="false" />
          <h4 class="missing-name">{{ ascended.name }}</h4>
          <p class="hint">{{ ascended.forbidden ? "Only by capture" : "Catch one, or buy copies in the shop" }}</p>
        </li>
      </ul>
    </template>

    <EmDialog class="ascended-details" :open="open !== null" :title="open?.name ?? 'Ascended details'" wide @close="openId = null">
      <div v-if="open" class="details" :class="{ 'tree-expanded': detailTab === 'tree' }">
        <aside class="summary">
          <img v-if="openInfo && spriteFor(openInfo.art, 'main_card')" class="detail-portrait" :src="spriteFor(openInfo.art, 'main_card')!" :style="{ objectPosition: `50% ${spriteFocus(openInfo.art, 'main_card')}%` }" :alt="open.name" />
          <h3 class="em-pixel name">{{ open.name }}</h3>
          <div class="copy-summary"><strong class="em-num">{{ open.copies }}</strong> {{ open.copies === 1 ? 'spare copy' : 'spare copies' }}<small>Available to spend on stars</small></div>
          <p class="level em-num">Level {{ open.level }} of {{ open.level_cap }}</p>
          <div class="badges">
            <EmTierBadge :tier-id="open.tier_id" />
            <span v-for="id in open.ascension_types" :key="id" class="type-chip"><TypeSymbol :type-id="id" :size="18" decorative />{{ typeLabel(id) }}</span>
          </div>

          <dl class="current-stats" aria-label="Current stats"><div v-for="stat in stats" :key="stat.key"><dt>{{ stat.key === 'hp' ? 'HP' : titleCase(stat.key) }}</dt><dd class="em-num">{{ stat.value }}</dd></div></dl>
          <p class="battle-status" :class="{ fainted: faintLeft > 0 }">{{ faintLeft > 0 ? `Fainted, ready in ${formatCountdown(faintLeft)}` : 'Ready for battle' }}</p>
          <div class="xp">
            <template v-if="open.xp_needed !== null">
              <EmBar :value="open.xp" :max="open.xp_needed" :label="`${open.name} XP`" />
              <span class="em-num">{{ open.xp }} / {{ open.xp_needed }} XP</span>
            </template>
            <span v-else>Highest level reached</span>
          </div>

          <div class="upgrade">
            <template v-if="open.stars_needed !== null">
              <EmBar :value="open.stars" :max="open.stars_needed" :label="`${open.name} stars`" />
              <span class="em-num">Stars {{ open.stars }} / {{ open.stars_needed }} to reach {{ titleCase(open.next_tier_id ?? "") }}</span>
              <span class="em-num">
                A star costs 1 spare copy and {{ open.star_essence_cost }} {{ titleCase(open.tier_id) }} essence.
                You have {{ open.copies }} {{ open.copies === 1 ? "copy" : "copies" }} and {{ essenceOf(open.tier_id) }} essence.
              </span>
              <div class="upgrade-actions">
                <EmButton v-if="open.can_tier_up" variant="primary" :disabled="store.busy" @click="raiseTier(open)">
                  Raise to {{ titleCase(open.next_tier_id ?? "") }}
                </EmButton>
                <EmButton v-else variant="primary" :disabled="!open.can_star_up || store.busy" @click="addStar(open)">Add a star</EmButton>
              </div>
            </template>
            <span v-else>Top of its ladder: no more stars.</span>
            <p v-if="upgradeMessage" class="upgrade-note" role="status">{{ upgradeMessage }}</p>
          </div>

          <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>
        </aside>
        <div class="side">
          <EmTabs v-model="detailTab" :options="detailTabs" ariaLabel="Ascended detail sections" @update:model-value="value => { if (value === 'tree') treeVisited = true; }" />
          <section v-if="detailTab === 'overview'" class="overview" role="tabpanel" aria-label="Overview">
            <div class="squad-control">
              <EmButton :disabled="!!squadReason || store.busy" :aria-busy="store.busy" @click="toggleSquad">{{ store.busy ? 'Saving squad…' : store.squadIds.includes(open.ascended_id) ? 'Remove from squad' : 'Add to squad' }}</EmButton>
              <p v-if="squadReason" class="muted">{{ squadReason }}</p>
            </div>
            <AscendedTemplateCard v-if="openInfo" class="big-card" :ascended="openInfo" :level="open.level" :tier-id="open.tier_id" />
            <div v-if="openInfo" class="overview-effects"><h4>Innate passive</h4><strong>{{ titleCase(openInfo.passive.kind) }}</strong><p>{{ passiveText(openInfo.passive.kind, openInfo.passive.params) }}</p><h4>Foundation abilities</h4><article v-for="ability in openInfo.abilities" :key="ability.id"><strong>{{ ability.name }}</strong><p>{{ abilityEffect(ability) }} · Level {{ ability.unlock_level }}</p></article><p class="muted">Manage learned abilities and your battle loadout in the Ability tree tab. The card shows base stats and growth; current stats are in the summary.</p></div>
          </section>
          <section v-show="detailTab === 'personalities'" role="tabpanel" aria-label="Personalities">
          <div class="people-head">
            <h4>Collected personalities</h4>
            <small class="em-num">{{ personalities.length }}{{ nextCursor !== null ? "+" : "" }} collected</small>
          </div>
          <EmNotice v-if="detailError" tone="error">{{ detailError }}</EmNotice>
          <p v-if="loadingMore" class="muted" role="status">Loading personalities…</p>
          <PresetEditor :key="open.ascended_id" :ascended-id="open.ascended_id" :ascended-name="open.name" :personalities="personalities" />
          <button v-if="nextCursor !== null" type="button" class="more" :disabled="loadingMore" @click="loadPersonalities(nextCursor)">
            Show more
          </button>
          </section>
          <section v-if="treeVisited" v-show="detailTab === 'tree'" role="tabpanel" aria-label="Ability tree"><TreeTab :key="open.ascended_id" :ascended="open" /></section>
        </div>
      </div>
    </EmDialog>
  </section>
</template>

<style scoped>
.squad-section h3 { margin: 0 0 var(--em-space-3); }
.squad-strip { display: flex; flex-wrap: wrap; gap: var(--em-space-3); padding: 0; margin: 0; list-style: none; }
.squad-slot { display: flex; flex-direction: column; gap: var(--em-space-2); width: 150px; }
.squad-slot :deep(.card) { --card-width: 100%; }
.squad-empty { min-height: 180px; justify-content: center; align-items: center; border: 1px dashed var(--em-border); border-radius: var(--em-radius); color: var(--em-muted); }
.squad-control { flex-basis: 100%; }
.squad-marker { display: inline-block; margin-top: var(--em-space-2); padding: var(--em-space-1) var(--em-space-2); border: 1px solid var(--em-accent); border-radius: var(--em-radius); color: var(--em-accent); font-size: 12px; }
.section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-3);
  margin: var(--em-space-6) 0 var(--em-space-4);
}
.section-head:first-child {
  margin-top: 0;
}
.section-head h3 {
  margin: 0;
  font-size: 18px;
  line-height: 1.4;
}
.section-head small {
  color: var(--em-muted);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 24px 20px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.empty {
  color: var(--em-muted);
}
.missing-ascended {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.back {
  width: 100%;
  margin-bottom: 6px;
  border-radius: var(--em-radius);
  filter: grayscale(0.4);
  opacity: 0.7;
  user-select: none;
}
.missing-name {
  margin: 0;
  font-size: 16px;
}
.hint {
  font-size: 12px;
  color: var(--em-muted);
}
.details {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  gap: var(--em-space-6);
}
.details.tree-expanded { grid-template-columns: minmax(0, 1fr); gap: var(--em-space-4); }
.tree-expanded .summary { display: grid; grid-template-columns: 1fr 1fr 1fr 220px; align-items: center; }
.tree-expanded .summary .detail-portrait,
.tree-expanded .summary .current-stats,
.tree-expanded .summary .battle-status,
.tree-expanded .summary .xp,
.tree-expanded .summary .upgrade { display: none; }
.tree-expanded .copy-summary { grid-column: 4; grid-row: 1; }
.collection :deep(.em-dialog.ascended-details) { width: min(1472px, calc(100vw - 32px)); }
.summary { display: flex; flex-direction: column; gap: var(--em-space-3); min-width: 0; }
.detail-portrait { width: 100%; height: 198px; object-fit: cover; border: 1px solid var(--em-divider); }
.copy-summary { padding: var(--em-space-3); background: var(--em-bg); border: 1px solid var(--em-accent); }
.copy-summary strong { font-size: 28px; margin-right: var(--em-space-2); }
.copy-summary small { display: block; color: var(--em-muted); font-size: 12px; }
.current-stats { display: flex; justify-content: space-between; margin: 0; padding: var(--em-space-3) 0; border-block: 1px solid var(--em-divider); }
.current-stats dt { color: var(--em-muted); font-size: 12px; }
.current-stats dd { margin: 0; font-size: 22px; font-weight: 600; }
.battle-status { color: var(--em-success); font-size: 13px; }
.battle-status.fainted { color: var(--em-danger); }
.overview { display: flex; flex-wrap: wrap; gap: var(--em-space-5); }
.overview-effects { flex: 1; min-width: 220px; display: flex; flex-direction: column; gap: var(--em-space-3); }
.overview-effects h4 { margin-top: var(--em-space-4); color: var(--em-accent); }
.overview-effects p { color: var(--em-muted); font-size: 13px; }
.overview-effects article { padding: var(--em-space-3); background: var(--em-bg); border: 1px solid var(--em-divider); }
.big-card {
  flex: none;
  --card-width: 340px;
  align-self: flex-start; /* a stretched flex item ignores the card's aspect ratio */
}
.side {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  gap: var(--em-space-5);
}
.name {
  margin: 0;
  font-size: 18px;
  line-height: 1.4;
}
.level {
  color: var(--em-muted);
}
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--em-space-2);
  align-items: center;
}
.type-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  color: var(--em-muted);
  font-size: 12px;
  font-weight: 600;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-3);
  margin-bottom: var(--em-space-4);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--em-space-2);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: var(--em-target);
  padding: 0 14px;
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  color: var(--em-text);
  background: var(--em-panel);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.chip[aria-pressed="true"] {
  border-color: var(--em-accent);
  color: var(--em-on-accent);
  background: var(--em-accent);
}
.group {
  margin-bottom: var(--em-space-5);
}
.group-name {
  display: flex;
  align-items: center;
  gap: var(--em-space-2);
  margin: 0 0 var(--em-space-3);
  font-size: 16px;
}
.group-name small {
  margin-left: var(--em-space-2);
  color: var(--em-muted);
}
.essences {
  display: flex;
  flex-wrap: wrap;
  gap: var(--em-space-3);
  margin: 0 0 var(--em-space-4);
  padding: 0;
  list-style: none;
}
.essences li {
  display: flex;
  align-items: center;
  gap: var(--em-space-2);
}
.upgrade {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 0 var(--em-space-3);
  font-size: 12px;
  color: var(--em-muted);
}
.upgrade-note {
  margin: 0;
  color: var(--em-text);
}
.upgrade-actions {
  display: flex;
  gap: var(--em-space-2);
}
.xp {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: var(--em-space-2) 0 var(--em-space-3);
  font-size: 12px;
  color: var(--em-muted);
}
.people-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--em-space-3);
  margin-top: var(--em-space-3);
}
.people-head h4 {
  margin: 0;
  font-size: 16px;
}
.people-head small {
  color: var(--em-muted);
}
.personalities {
  margin: 0;
  padding: 0;
  list-style: none;
}
.personalities li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-3);
  padding: 12px 0;
  border-bottom: 1px solid var(--em-divider);
  font-size: 13px;
}
.more {
  align-self: flex-start;
  min-height: var(--em-target);
  padding: 0 4px;
  border: 0;
  color: var(--em-accent);
  background: none;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
@media (max-width: 700px) {
  .tree-expanded .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tree-expanded .copy-summary { grid-column: 2; grid-row: 1 / span 2; }
  .details { grid-template-columns: minmax(0, 1fr); gap: var(--em-space-5); }
  .summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
  .summary .detail-portrait { height: 160px; grid-row: span 3; }
  .summary .current-stats, .summary .xp, .summary .upgrade, .summary .battle-status { grid-column: 1 / -1; }
  .summary .name { display: none; }
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 24px 18px;
  }
  .big-card {
    --card-width: 100%;
    max-width: 440px;
    margin: 0 auto;
  }
}
</style>
