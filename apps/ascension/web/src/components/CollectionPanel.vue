<script setup lang="ts">
import { computed, ref } from "vue";
import { useAscensionClient, type OwnedAscended, type PersonalityItem } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { errorMessage } from "../utils/errors";
import { filterByType, groupByType, typeLabel, typesPresent } from "../utils/ascensionTypes";
import { formatCountdown, titleCase, passiveText, abilityEffect } from "../utils/ascension";
import { spriteFor, spriteFocus } from "../utils/sprites";
import { useNowSeconds } from "../composables/useNowSeconds";
import TreeTab from "./TreeTab.vue";
import PresetEditor from "./PresetEditor.vue";
import AscendedCard from "./AscendedCard.vue";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmBar from "./ui/EmBar.vue";
import EmButton from "./ui/EmButton.vue";
import EmDialog from "./ui/EmDialog.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmSwitch from "./ui/EmSwitch.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";
import EmTabs from "./ui/EmTabs.vue";
import TypeSymbol from "./ui/TypeSymbol.vue";

/** Collection filters, squad strip and selected Ascended inspector, with full
 * progression, personalities and ability-tree operations in the details dialog. */
const store = useAscensionStore();
const ascensionClient = useAscensionClient();
const PAGE_SIZE = 50;

const typeFilter = ref<string | null>(null);
const grouped = ref(false);
const search = ref("");
const rarity = ref("");
const showUncollected = ref(true);
const matches = (name: string, tier: string) => name.toLowerCase().includes(search.value.trim().toLowerCase()) && (!rarity.value || tier === rarity.value);
const allOwned = computed(() => store.profile?.ascendeds ?? []);
const allNotOwned = computed(() => {
  const ids = new Set(allOwned.value.map((s) => s.ascended_id));
  return (store.catalog?.ascendeds ?? []).filter((s) => !ids.has(s.id));
});
/** The types to offer as filters: those any Ascended in the catalog has. */
const types = computed(() => typesPresent(store.catalog?.ascendeds ?? []));
const catalogById = computed(() => new Map((store.catalog?.ascendeds ?? []).map(info => [info.id, info])));
/** Squad members show in the squad strip, so the collected list leaves them out. */
const owned = computed(() => filterByType(allOwned.value.filter((s) => !s.in_squad && matches(s.name, s.tier_id)), typeFilter.value));
const notOwned = computed(() => filterByType(allNotOwned.value.filter(s => matches(s.name, s.start_tier)), typeFilter.value));
const groups = computed(() => groupByType(owned.value));

const openId = ref<string | null>(null);
const detailsOpen = ref(false);
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
  if (id === null || !fromSquad || store.busy || battleActive.value || store.squadIds.length <= 1) return;
  await store.removeFromSquad(id);
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
    <aside class="filter-rail" aria-label="Collection filters">
      <h3 class="em-pixel">Filters</h3>
      <label class="filter-label">Search<input v-model="search" type="search" placeholder="Find an Ascended" aria-label="Search collection" /></label>
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

      <label class="filter-label">Rarity<select v-model="rarity" aria-label="Filter by rarity"><option value="">All rarities</option><option v-for="tier in store.catalog?.tiers" :key="tier.id" :value="tier.id">{{ titleCase(tier.id) }}</option></select></label>
      <label class="uncollected"><input v-model="showUncollected" type="checkbox" aria-label="Show uncollected" />Show uncollected</label>
      <p class="rail-count em-num">{{ allOwned.length }} / {{ store.catalog?.ascendeds.length ?? 0 }} collected</p>
    </aside>
    <main class="collection-main">
    <ul v-if="essences.length" class="essences" aria-label="Essence">
      <li v-for="[tierId, count] in essences" :key="tierId" :style="{ '--tier': `var(--em-tier-${tierId}, var(--em-tier-common))` }">
        <EmTierBadge :tier-id="tierId" :label="`${titleCase(tierId)} essence`" /> <strong class="em-num">{{ count }}</strong>
      </li>
    </ul>
    <section class="squad-section" aria-label="Squad">
      <h3 class="em-pixel">Your squad <small class="em-num">{{ store.squadIds.length }} / {{ store.profile?.squad_size }}</small></h3>
      <ul class="squad-strip">
        <li v-for="(member, index) in squadSlots" :key="index" class="squad-slot" :class="{ 'squad-empty': !member, selected: member?.ascended_id === openId, 'drop-over': dragId !== null && overSlot === index }" @dragover="dragOverSlot($event, index)" @dragleave="overSlot = null" @drop.prevent="dropOnSlot(index)">
          <template v-if="member">
            <div
              v-if="store.catalog?.ascendeds.find(a => a.id === member.ascended_id)"
              class="squad-card em-lift"
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
              <img v-if="spriteFor(catalogById.get(member.ascended_id)?.art, 'battle')" class="squad-portrait" :src="spriteFor(catalogById.get(member.ascended_id)?.art, 'battle')!" alt="" draggable="false" />
              <span v-else class="squad-placeholder">◇</span>
              <div class="squad-member-info"><strong>{{ member.name }}</strong><span class="em-num">Lv. {{ member.level }}</span><span class="squad-stars em-num">★ {{ member.stars }}</span><div class="squad-types"><TypeSymbol v-for="id in member.ascension_types" :key="id" :type-id="id" :size="18" decorative /><EmTierBadge :tier-id="member.tier_id" /></div></div>
            </div>
            <EmButton :disabled="store.squadIds.length <= 1 || battleActive || store.busy" :aria-label="`Remove ${member.name} from squad`" :aria-busy="store.busy" @click="store.removeFromSquad(member.ascended_id)">Remove</EmButton>
          </template>
          <span v-else>Empty slot</span>
        </li>
      </ul>
      <p v-if="battleActive" class="muted">Finish your battle first.</p>
    </section>

    <div class="collected-zone" :class="{ 'drop-over': overCollected }" @dragover="dragOverCollected" @dragleave="overCollected = false" @drop.prevent="dropOnCollected">
      <div class="section-head">
        <h3 class="em-pixel">Collected <small class="em-num">{{ owned.length }}</small></h3>
        <small>Select an Ascended to inspect</small>
      </div>
      <template v-if="grouped">
        <section v-for="group in groups" :key="group.typeId ?? 'none'" class="group" :data-type="group.typeId ?? 'none'">
          <h4 class="group-name"><TypeSymbol v-if="group.typeId" :type-id="group.typeId" :size="40" decorative />{{ group.label }} <small class="em-num">{{ group.items.length }}</small></h4>
          <div class="grid">
            <div v-for="ascended in group.items" :key="ascended.ascended_id" class="owned-entry" draggable="true" @dragstart="dragStart($event, ascended.ascended_id, false)" @dragend="dragEnd">
              <AscendedCard :ascended="ascended" :selected="openId === ascended.ascended_id" @open="show(ascended)" />
            </div>
          </div>
        </section>
      </template>
      <div v-else class="grid">
        <div v-for="ascended in owned" :key="ascended.ascended_id" class="owned-entry" draggable="true" @dragstart="dragStart($event, ascended.ascended_id, false)" @dragend="dragEnd">
          <AscendedCard :ascended="ascended" :selected="openId === ascended.ascended_id" @open="show(ascended)" />
        </div>
      </div>
      <p v-if="owned.length === 0" class="empty">{{ allOwned.length > owned.length && typeFilter === null ? "Everyone you collected is in your squad." : typeFilter === null ? "None collected yet." : `No ${typeLabel(typeFilter)} Ascended collected yet.` }}</p>

    </div>

    <template v-if="showUncollected && notOwned.length">
      <div class="section-head">
        <h3 class="em-pixel">Not collected yet</h3>
        <small>{{ notOwned.length }} still to find</small>
      </div>
      <ul class="grid missing">
        <li v-for="ascended in notOwned" :key="ascended.id" class="missing-ascended em-lift" :style="{ '--tier': 'var(--em-border)' }">
          <AscendedPreviewCard class="back" :ascended="ascended" :tier-id="ascended.start_tier" flipped />
          <h4 class="missing-name">{{ ascended.name }}</h4>
          <p class="hint">{{ ascended.forbidden ? "Only by capture" : "Catch one, or buy copies in the shop" }}</p>
        </li>
      </ul>
    </template>

    </main>
    <aside class="collection-inspector" aria-label="Selected Ascended">
      <template v-if="open">
        <small class="em-eyebrow">Selected Ascended</small>
        <img v-if="openInfo && spriteFor(openInfo.art, 'battle')" class="inspector-portrait" :src="spriteFor(openInfo.art, 'battle')!" :alt="open.name" />
        <div class="inspector-title"><h3>{{ open.name }}</h3><EmTierBadge :tier-id="open.tier_id" /><span class="em-num">Lv. {{ open.level }}</span></div>
        <dl class="current-stats"><div v-for="stat in stats" :key="stat.key"><dt>{{ stat.key === 'hp' ? 'HP' : titleCase(stat.key) }}</dt><dd class="em-num">{{ stat.value }}</dd></div></dl>
        <p class="inspector-copies em-num">{{ open.copies }} spare {{ open.copies === 1 ? 'copy' : 'copies' }}</p>
        <p class="battle-status" :class="{ fainted: faintLeft > 0 }">{{ faintLeft > 0 ? 'Resting · ' + formatCountdown(faintLeft) : 'Ready for battle' }}</p>
        <EmButton class="open-details" variant="primary" @click="detailsOpen = true">Open details</EmButton>
        <EmButton :disabled="!!squadReason || store.busy" @click="toggleSquad">{{ store.squadIds.includes(open.ascended_id) ? 'Remove from squad' : 'Add to squad' }}</EmButton>
        <p v-if="squadReason" class="muted inspector-reason">{{ squadReason }}</p>
      </template>
      <template v-else><div class="inspector-empty">◇</div><h3>Your Ascended</h3><p class="muted">Select a squad member or a collected card to see its stats and progression.</p></template>
    </aside>
    <EmDialog class="ascended-details" :open="detailsOpen && open !== null" :title="open?.name ?? 'Ascended details'" wide @close="detailsOpen = false">
      <div v-if="open && detailsOpen" class="details" :class="{ 'tree-expanded': detailTab !== 'overview' }">
        <aside class="summary">
          <img v-if="openInfo && spriteFor(openInfo.art, 'battle')" class="detail-portrait" :src="spriteFor(openInfo.art, 'battle')!" :style="{ objectPosition: `50% ${spriteFocus(openInfo.art, 'battle')}%` }" :alt="open.name" />
          <h3 class="em-pixel name">{{ open.name }}</h3>
          <div class="copy-summary"><strong class="em-num">{{ open.copies }}</strong> {{ open.copies === 1 ? 'spare copy' : 'spare copies' }}<small>Available to spend on stars</small></div>
          <p class="level em-num">Level {{ open.level }} of {{ open.level_cap }}</p>
          <div class="badges">
            <EmTierBadge :tier-id="open.tier_id" />
            <span v-for="id in open.ascension_types" :key="id" class="type-chip"><TypeSymbol :type-id="id" :size="18" decorative />{{ typeLabel(id) }}</span>
          </div>

          <p class="battle-status" :class="{ fainted: faintLeft > 0 }">{{ faintLeft > 0 ? `Fainted, ready in ${formatCountdown(faintLeft)}` : 'Ready for battle' }}</p>
            <div class="squad-control">
              <EmButton :disabled="!!squadReason || store.busy" :aria-busy="store.busy" @click="toggleSquad">{{ store.busy ? 'Saving squad…' : store.squadIds.includes(open.ascended_id) ? 'Remove from squad' : 'Add to squad' }}</EmButton>
              <p v-if="squadReason" class="muted">{{ squadReason }}</p>
            </div>
          <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>
        </aside>
        <div class="side">
          <EmTabs v-model="detailTab" :options="detailTabs" ariaLabel="Ascended detail sections" @update:model-value="value => { if (value === 'tree') treeVisited = true; }" />
          <section v-if="detailTab === 'overview'" class="overview" role="tabpanel" aria-label="Overview">
            <div class="stats-panel"><h4 class="em-pixel">Stats & experience</h4>
              <dl class="current-stats" aria-label="Current stats"><div v-for="stat in stats" :key="stat.key"><dt>{{ stat.key === 'hp' ? 'HP' : titleCase(stat.key) }}</dt><dd class="em-num">{{ stat.value }}</dd></div></dl>
          <div class="xp">
            <template v-if="open.xp_needed !== null">
              <EmBar :value="open.xp" :max="open.xp_needed" :label="`${open.name} XP`" />
              <span class="em-num">{{ open.xp }} / {{ open.xp_needed }} XP</span>
            </template>
            <span v-else>Highest level reached</span>
          </div>

            </div>
            <div v-if="openInfo" class="overview-effects"><h4>Innate passive</h4><strong>{{ titleCase(openInfo.passive.kind) }}</strong><p>{{ passiveText(openInfo.passive.kind, openInfo.passive.params) }}</p><h4>Foundation abilities</h4><article v-for="ability in openInfo.abilities" :key="ability.id"><strong>{{ ability.name }}</strong><p>{{ abilityEffect(ability) }} · Level {{ ability.unlock_level }}</p></article><p class="muted">Manage learned abilities and your battle loadout in the Ability tree tab. </p></div>
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
        <aside v-if="detailTab === 'overview'" class="progression-panel" aria-label="Progression"><h3 class="em-pixel">Progression</h3><div class="progression-resources"><div><small>Spare copies</small><strong class="em-num">{{ open.copies }}</strong></div><div><small>{{ titleCase(open.tier_id) }} essence</small><strong class="em-num">{{ essenceOf(open.tier_id) }}</strong></div></div><h4 class="em-pixel">Star progression</h4>
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

        </aside>
      </div>
    </EmDialog>
  </section>
</template>

<style scoped>
.collection { display: grid; grid-template-columns: 184px minmax(0, 1fr) 276px; gap: 18px; align-items: start; }
.filter-rail, .collection-inspector, .summary, .progression-panel, .stats-panel, .overview-effects { border: 1px solid var(--em-border); background: linear-gradient(135deg, var(--em-panel), var(--em-bg)); box-shadow: inset 0 0 0 3px rgb(255 255 255 / 2%); }
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
.squad-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; padding: 0; margin: 0; list-style: none; }
.squad-slot { min-width: 0; border: 1px solid var(--em-border); padding: 6px; background: var(--em-panel); display: flex; flex-direction: column; gap: 6px; }
.squad-slot.selected { border-color: var(--em-accent); box-shadow: 0 0 0 1px var(--em-accent); }
.squad-card { cursor: pointer; min-width: 0; display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; align-items: center; min-height: 100px; }
.squad-portrait, .squad-placeholder { width: 64px; height: 94px; object-fit: contain; image-rendering: pixelated; background: #060d15; }
.squad-placeholder { display: grid; place-items: center; color: var(--em-muted); font-size: 32px; }
.squad-member-info { display: flex; flex-direction: column; gap: 5px; overflow-wrap: anywhere; }
.squad-member-info strong { font-size: 13px; }
.squad-member-info > span { font-size: 12px; color: var(--em-muted); }
.squad-member-info .squad-stars { color: var(--em-accent); }
.squad-types { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.squad-card :deep(.card) { --card-width: 100%; }
.squad-slot :deep(.em-btn) { min-height: 30px; font-size: 11px; padding: 3px 8px; }
.squad-empty { min-height: 142px; justify-content: center; align-items: center; border-style: dashed; color: var(--em-muted); font-size: 12px; }
.drop-over { outline: 2px dashed var(--em-accent); outline-offset: 4px; }
.section-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin: 22px 0 12px; }
.section-head h3 { margin: 0; font-size: 15px; }
.section-head small { color: var(--em-muted); font-size: 11px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(136px, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
.owned-entry { min-width: 0; }
.empty { color: var(--em-muted); font-size: 13px; padding-block: 12px; }
.missing-ascended { min-width: 0; display: flex; flex-direction: column; gap: 5px; padding: 6px; border: 1px dashed var(--em-border); background: var(--em-bg); }
.back { --card-width: 100%; opacity: .6; }
.missing-name { margin: 0; font-size: 13px; }
.hint { color: var(--em-muted); font-size: 11px; margin: 0; }
.collection-inspector { min-width: 0; padding: 16px; position: sticky; top: 18px; display: flex; flex-direction: column; gap: 12px; }
.inspector-portrait { width: 100%; height: 230px; object-fit: contain; image-rendering: pixelated; background: #060d15; border: 1px solid var(--em-border); }
.inspector-title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.inspector-title h3 { flex-basis: 100%; margin: 0; font-size: 20px; }
.inspector-title > span { color: var(--em-muted); font-size: 13px; }
.inspector-copies { border-bottom: 1px solid var(--em-divider); padding-bottom: 12px; font-size: 13px; margin: 0; }
.inspector-empty { height: 180px; display: grid; place-items: center; color: var(--em-border); font-size: 96px; }
.inspector-reason { font-size: 12px; text-align: center; }
.essences { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 14px; padding: 0; list-style: none; }
.essences li { display: flex; gap: 6px; align-items: center; font-size: 12px; }
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
.upgrade-actions :deep(.em-btn) { width: 100%; }
.upgrade-note { color: var(--em-text); }
.people-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.people-head h4 { margin: 0; font-size: 15px; }
.people-head small { color: var(--em-muted); font-size: 12px; }
.more { min-height: 44px; color: var(--em-accent); background: transparent; border: 0; font: inherit; cursor: pointer; }
button:focus-visible, input:focus-visible, select:focus-visible, .squad-card:focus-visible { outline: 2px solid var(--em-accent); outline-offset: 3px; }
@media (max-width: 1180px) { .collection { grid-template-columns: 160px minmax(0, 1fr) 230px; gap: 12px; } .details { grid-template-columns: 180px minmax(0, 1fr); } .progression-panel { grid-column: 2; } .inspector-portrait { height: 190px; } }
@media (max-width: 900px) { .details { height: auto; } .details.tree-expanded .side { grid-column: 1; } .details > * { overflow-y: visible; } .collection { grid-template-columns: 150px minmax(0, 1fr); } .collection-inspector { position: static; grid-column: 2; display: grid; grid-template-columns: 120px minmax(0, 1fr); } .inspector-portrait { grid-column: 1; grid-row: 2 / span 3; height: 140px; } .collection-inspector .current-stats { grid-column: 2; } .collection-inspector .open-details, .collection-inspector > .em-btn { grid-column: 1 / -1; } .details.tree-expanded { grid-template-columns: minmax(0, 1fr); } .tree-expanded .summary { display: grid; grid-template-columns: 100px minmax(0, 1fr); align-items: start; } .tree-expanded .summary .detail-portrait { grid-row: 1 / span 4; height: 150px; } .tree-expanded .summary .battle-status, .tree-expanded .summary .squad-control { grid-column: 1 / -1; } }
@media (max-width: 600px) { .collection { grid-template-columns: minmax(0, 1fr); } .filter-rail { position: static; gap: 12px; } .chips { flex-direction: row; flex-wrap: wrap; } .filters { gap: 12px; } .collection-inspector { grid-column: 1; } .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .squad-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .squad-card { grid-template-columns: 48px minmax(0, 1fr); } .squad-portrait, .squad-placeholder { width: 48px; height: 80px; } .squad-empty { min-height: 90px; } .details { grid-template-columns: minmax(0, 1fr); } .summary { display: grid; grid-template-columns: 100px minmax(0, 1fr); } .summary .detail-portrait { grid-row: span 4; height: 150px; } .summary .battle-status { grid-column: 1 / -1; } .progression-panel { grid-column: 1; } .collection :deep(.em-dialog.ascended-details) { padding: 14px; } }
</style>
