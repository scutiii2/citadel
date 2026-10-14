<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { newIdempotencyKey, type ShopOffer } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { useShopBasketStore, type BasketItem, type ShopMode } from "../stores/shopBasket";
import { formatCountdown, titleCase } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmButton from "./ui/EmButton.vue";
import EmEmblem from "./ui/EmEmblem.vue";
import EmConfirm from "./ui/EmConfirm.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmNotice from "./ui/EmNotice.vue";
import EmQuantity from "./ui/EmQuantity.vue";
import EmDialog from "./ui/EmDialog.vue";

const store = useAscensionStore();
const basket = useShopBasketStore();
const { mode, processing, message, interrupted } = storeToRefs(basket);
const baskets = basket.baskets;
const category = ref("all");
const rarity = ref("");
const search = ref("");
const hideUnavailable = ref(false);
const reviewOpen = ref(false);
const basketOpen = ref(false);
const filtersOpen = ref(false);
const portrait = ref(false);
let compactQuery: MediaQueryList | undefined;
function updateCompact(): void {
  portrait.value = compactQuery?.matches ?? false;
  basketOpen.value = false;
}
let alive = true;
const now = useNowSeconds();
const secondsLeft = computed(() => Math.max(0, store.shopEndsAt - now.value));
const insignia = computed(() => store.profile?.insignia ?? 0);
const tiers = computed(() => store.catalog?.tiers ?? []);
const offers = computed(() => store.shop?.offers ?? []);
const items = computed(() => baskets[mode.value]);
const total = computed(() => items.value.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0));
const requiredFunds = computed(() => items.value.filter(item => !item.requestKey).reduce((sum, item) => sum + item.quantity * item.unitPrice, 0));
const awaitingAcknowledgement = computed(() => items.value.some(item => item.requestKey));
const units = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0));
const balanceAfter = computed(() => insignia.value + (mode.value === "buy" ? -total.value : total.value));
const locked = computed(() => processing.value || store.busy || reviewOpen.value);
const canCheckout = computed(() => !locked.value && items.value.length > 0 && items.value.every(item => !problem(item)) && (mode.value === "sell" || requiredFunds.value <= insignia.value));
const nameOf = (id: string) => store.catalog?.ascendeds.find(a => a.id === id)?.name ?? titleCase(id);
const ascendedOf = (id: string) => store.catalog?.ascendeds.find(a => a.id === id);
const money = (value: number) => value.toLocaleString();
const matches = (name: string, tierId: string) => (!rarity.value || rarity.value === tierId) && name.toLowerCase().includes(search.value.trim().toLowerCase());

function fighting(id: string): boolean {
  if (!store.profile?.active_battle && store.battle?.status !== "active") return false;
  return !store.battle || store.battle.player.ascended_id === id;
}
const visibleOffers = computed(() => category.value === "emblems" ? [] : offers.value.filter(o => matches(nameOf(o.ascended_id), o.tier_id)));
const visibleTiers = computed(() => category.value === "offers" ? [] : tiers.value.filter(t => matches(titleCase(t.id) + " EMBLEM", t.id)));
const sellable = computed(() => (store.profile?.ascendeds ?? []).filter(a => matches(a.name, a.tier_id) && (!hideUnavailable.value || (a.copies > 0 && !fighting(a.ascended_id)))));
const saleReview = computed(() => baskets.sell.map(item => item.name + " × " + item.quantity + " — " + money(item.quantity * item.unitPrice) + " Insignia").join("; ") + ". Only spare copies are sold. Your Ascended stays in your collection.");
const offerKey = (offer: ShopOffer) => "offer:" + store.shop?.rotation + ":" + offer.slot;
const selected = (key: string) => items.value.find(item => item.key === key);
const offerOff = (offer: ShopOffer) => offer.left <= 0 || offer.price > insignia.value || fighting(offer.ascended_id) || !store.shop || secondsLeft.value <= 0;
const selection = (item: BasketItem) => items.value.some(i => i.key === item.key);

function available(item: BasketItem): number {
  if (item.kind === "emblem") return 99;
  if (item.kind === "sale") return store.profile?.ascendeds.find(a => a.ascended_id === item.id)?.copies ?? 0;
  if (item.rotation !== store.shop?.rotation) return 0;
  return offers.value.find(o => o.slot === item.slot)?.left ?? 0;
}
function problem(item: BasketItem): string {
  // Resolve a prior attempt using its frozen payload/key. It may already have consumed stock or funds.
  if (item.requestKey) return "";
  if (item.kind === "offer") {
    if (item.rotation !== store.shop?.rotation || secondsLeft.value <= 0) return "Expired offer · remove and choose again";
    const offer = offers.value.find(o => o.slot === item.slot);
    if (!offer || offer.ascended_id !== item.id) return "Offer unavailable";
    if (offer.price !== item.unitPrice || offer.copies_granted !== item.copiesPerPack) return "Price changed · remove and add again";
  }
  if (item.kind === "emblem") {
    if (tiers.value.find(t => t.id === item.id)?.emblem_price !== item.unitPrice) return "Price changed · remove and add again";
  }
  if (item.kind === "sale") {
    const owned = store.profile?.ascendeds.find(a => a.ascended_id === item.id);
    if (!owned || owned.sale_value !== item.unitPrice) return "Price changed · remove and add again";
  }
  if (item.kind !== "emblem" && fighting(item.id)) return "In active battle";
  if (item.quantity > available(item)) return "Not enough stock · reduce quantity";
  return "";
}
function add(item: BasketItem): void {
  if (locked.value || selection(item)) return;
  items.value.push(item);
  message.value = "";
}
function addOffer(offer: ShopOffer): void {
  if (offerOff(offer)) return;
  add({ key: offerKey(offer), kind: "offer", id: offer.ascended_id, name: nameOf(offer.ascended_id), tierId: offer.tier_id, unitPrice: offer.price, quantity: 1, rotation: store.shop!.rotation, slot: offer.slot, copiesPerPack: offer.copies_granted });
}
function setQuantity(item: BasketItem, value: number): void {
  if (locked.value || item.requestKey) return;
  item.quantity = Math.min(Math.max(1, Math.floor(Number.isFinite(value) ? value : 1)), Math.max(1, available(item)));
}
function quantityInput(item: BasketItem, event: Event): void {
  setQuantity(item, Number((event.target as HTMLInputElement).value));
  (event.target as HTMLInputElement).value = String(item.quantity);
}
function remove(item: BasketItem): void {
  if (!locked.value) baskets[mode.value] = items.value.filter(i => i.key !== item.key);
}
function switchMode(next: ShopMode): void {
  if (locked.value) return;
  mode.value = next;
  category.value = "all";
  search.value = "";
  rarity.value = "";
}
function checkout(): void {
  if (!canCheckout.value) return;
  if (mode.value === "sell") reviewOpen.value = true;
  else void trade();
}

/** Existing endpoints settle independently. Remove each successful unit immediately, retain the rest on failure. */
async function trade(): Promise<void> {
  if (processing.value || store.busy) return;
  const side = mode.value;
  const owner = store.profile?.owner;
  const batch = [...baskets[side]];
  if (batch.length === 0 || batch.some(item => problem(item)) || (side === "buy" && requiredFunds.value > insignia.value)) {
    reviewOpen.value = false;
    return;
  }
  reviewOpen.value = false;
  processing.value = true;
  interrupted.value = false;
  message.value = "";
  let completed = 0;
  let amount = 0;
  let stopped = "";
  try {
    // Revalidate offers before the first mutation, as a rotation can change while the basket is open.
    if (batch.some(item => item.kind === "offer")) await store.loadShop();
    for (const item of batch) {
      while (item.quantity > 0) {
        if (!alive || store.profile?.owner !== owner) { stopped = "Account or screen changed"; break; }
        const issue = problem(item);
        if (issue) { stopped = issue; break; }
        if (!item.requestKey && item.kind !== "sale" && item.unitPrice * (item.kind === "emblem" ? item.quantity : 1) > insignia.value) {
          stopped = "Not enough Insignia";
          break;
        }
        const quantity = item.kind === "emblem" ? item.quantity : 1;
        item.requestKey ??= newIdempotencyKey();
        let result;
        if (item.kind === "offer") {
          result = await store.buyOffer({ slot: item.slot! }, item.requestKey, item.rotation);
        } else if (item.kind === "emblem") result = await store.buyEmblems(item.id, quantity, item.requestKey);
        else result = await store.sellCopy(item.id, item.requestKey);
        if (!result) { stopped = store.error || "Trade could not complete"; break; }
        if (store.profile?.owner !== owner) break;
        completed += quantity;
        item.requestKey = undefined;
        amount += "price" in result ? result.price : result.value;
        item.quantity -= quantity;
        if (item.quantity === 0) baskets[side] = baskets[side].filter(i => i.key !== item.key);
      }
      if (!alive && baskets[side].length) stopped ||= "Screen changed";
      if (stopped || !alive || store.profile?.owner !== owner) break;
    }
  } finally {
    processing.value = false;
    if (store.profile?.owner === owner) {
      interrupted.value = Boolean(stopped);
      const summary = side === "buy" ? "Purchased " + completed + " units for " + money(amount) + " Insignia." : "Sold " + completed + " spare copies for " + money(amount) + " Insignia.";
      message.value = summary + (stopped ? " Stopped: " + stopped + ". Remaining items are still in your basket." : "");
    }
  }
}

onMounted(() => {
  void store.loadShop();
  compactQuery = window.matchMedia?.('(orientation: portrait), (max-width: 760px)');
  updateCompact();
  compactQuery?.addEventListener('change', updateCompact);
});
onUnmounted(() => { alive = false; compactQuery?.removeEventListener('change', updateCompact); });
watch(() => secondsLeft.value <= 0 && store.shop !== null, over => { if (over) void store.loadShop(); });
watch(() => store.profile?.owner, () => { reviewOpen.value = false; });
</script>

<template>
  <section class="shop" :aria-busy="processing">
    <h2 class="page-heading">Shop</h2>
    <p class="page-intro">Acquire new allies and stock up on EMBLEMs.</p>
    <div class="shop-toolbar">
      <div class="mode-tabs" role="group" aria-label="Shop mode">
        <button type="button" data-mode="buy" aria-label="Buy" :aria-pressed="mode === 'buy'" :disabled="locked" @click="switchMode('buy')"><EmIcon name="shop" />Offers</button>
        <button type="button" data-mode="sell" aria-label="Sell" :aria-pressed="mode === 'sell'" :disabled="locked" @click="switchMode('sell')"><EmIcon name="coin" />Sell Copies</button>
      </div>
      <input v-model="search" class="shop-search" type="search" placeholder="Search items…" aria-label="Search shop" :disabled="locked" />
      <small v-if="mode === 'buy'" class="refresh em-num"><EmIcon name="clock" />Refreshes in {{ formatCountdown(secondsLeft) }}</small>
    </div>
    <p v-if="message && (!portrait || !basketOpen)" class="notice" :class="{ interrupted }" role="status"><EmIcon :name="interrupted ? 'warning' : 'check'" />{{ message }}</p>
    <EmNotice v-if="store.error && (!portrait || !basketOpen)" tone="error">{{ store.error }}</EmNotice>
    <div class="trading-floor">
      <button class="filter-toggle" type="button" :aria-expanded="filtersOpen" aria-controls="shop-filters" @click="filtersOpen = !filtersOpen"><EmIcon name="settings" />Filters</button>
      <aside id="shop-filters" class="category-rail" :class="{ expanded: filtersOpen }" aria-label="Shop filters">
        <p class="em-eyebrow">Browse</p>
        <template v-if="mode === 'buy'">
          <button v-for="c in [{ id: 'all', name: 'All items', icon: 'shop' as const }, { id: 'offers', name: 'Ascended offers', icon: 'ascended' as const }, { id: 'emblems', name: 'EMBLEMs', icon: 'shield' as const }]" :key="c.id" type="button" :aria-pressed="category === c.id" :disabled="locked" @click="category = c.id"><EmIcon :name="c.icon" />{{ c.name }}</button>
        </template>
        <div v-else class="rail-selected"><EmIcon name="ascended" />Spare copies</div>
        <label v-if="mode === 'sell'" class="rail-field"><span class="em-eyebrow">Rarity</span><select v-model="rarity" :disabled="locked" aria-label="Filter shop by rarity"><option value="">All rarities</option><option v-for="t in tiers" :key="t.id" :value="t.id">{{ titleCase(t.id) }}</option></select></label>
        <label v-if="mode === 'sell'" class="hide-unavailable"><input v-model="hideUnavailable" type="checkbox" :disabled="locked" />Hide unavailable</label>
        <div class="rail-note"><EmIcon :name="mode === 'buy' ? 'clock' : 'shield'" /><p>{{ mode === 'buy' ? 'Offers are yours alone. New stock every rotation.' : 'Sell only spare copies. Your collected Ascended stays with you.' }}</p></div>
      </aside>

      <div class="shop-catalog">
        <div :class="mode === 'buy' ? 'offer-groups' : 'item-grid'">
          <template v-if="mode === 'buy'">
            <section v-if="visibleOffers.length" class="catalog-group" aria-label="Ascended offers">
            <h3 class="group-heading">Ascended offers <small>{{ visibleOffers.length }}</small></h3>
            <div class="item-grid">
            <article v-for="offer in visibleOffers" :key="offerKey(offer)" class="item-card ascended-offer" :class="{ 'is-off': offerOff(offer), selected: selected(offerKey(offer)) }" :data-offer="offer.slot" :style="{ '--tier': 'var(--em-tier-' + offer.tier_id + ')' }">
              <div class="item-art"><AscendedPreviewCard v-if="ascendedOf(offer.ascended_id)" :ascended="ascendedOf(offer.ascended_id)!" :tier-id="offer.tier_id" art-slot="preview_card" /><span v-else class="letter">{{ nameOf(offer.ascended_id).slice(0, 1) }}</span></div>
              <div class="item-actions offer-details">
                <p class="pack-size">{{ offer.copies_granted }} {{ offer.copies_granted === 1 ? 'copy' : 'copies' }} / pack</p>
                <p class="offer-stock">{{ offer.left <= 0 ? 'Sold out' : offer.left + ' left' }}</p>
                <p class="item-price em-num"><EmIcon name="coin" />{{ money(offer.price) }} <small>/ pack</small></p>
                <div class="selection-slot"><small v-if="selected(offerKey(offer))" class="in-basket"><EmIcon name="check" :size="12" />In basket</small></div>
              <EmQuantity v-if="selected(offerKey(offer))" :quantity="selected(offerKey(offer))!.quantity" :max="available(selected(offerKey(offer))!)" :name="selected(offerKey(offer))!.name" :disabled="locked || !!selected(offerKey(offer))!.requestKey" @change="setQuantity(selected(offerKey(offer))!, $event)" />
              <EmButton v-else data-add :variant="selected(offerKey(offer)) ? 'primary' : 'secondary'" :disabled="locked || offerOff(offer) || !!selected(offerKey(offer))" @click="addOffer(offer)">{{ selected(offerKey(offer)) ? 'In basket' : offer.left <= 0 ? 'Sold out' : fighting(offer.ascended_id) ? 'In active battle' : '+ Add' }}</EmButton>
              </div>
            </article>
            </div>
            </section>
            <section v-if="visibleTiers.length" class="catalog-group" aria-label="EMBLEMs">
            <h3 class="group-heading">EMBLEMs <small>{{ visibleTiers.length }}</small></h3>
            <div class="item-grid emblem-grid">
            <article v-for="t in visibleTiers" :key="t.id" class="item-card" :class="{ 'is-off': t.emblem_price > insignia, selected: selected('emblem:' + t.id) }" :data-tier="t.id" :style="{ '--tier': 'var(--em-tier-' + t.id + ')' }">
              <div class="item-art"><EmEmblem :tier-id="t.id" :size="40" /></div>
              <div class="item-info"><h4>{{ titleCase(t.id) }} EMBLEM</h4><p class="item-price em-num"><EmIcon name="coin" />{{ money(t.emblem_price) }} <small>each</small></p></div>
              <div class="item-actions">
              <EmQuantity v-if="selected('emblem:' + t.id)" :quantity="selected('emblem:' + t.id)!.quantity" :max="available(selected('emblem:' + t.id)!)" :name="selected('emblem:' + t.id)!.name" :disabled="locked || !!selected('emblem:' + t.id)!.requestKey"  @change="setQuantity(selected('emblem:' + t.id)!, $event)" />
              <EmButton v-else data-add :variant="selected('emblem:' + t.id) ? 'primary' : 'secondary'" :disabled="locked || t.emblem_price > insignia || !!selected('emblem:' + t.id)" @click="add({ key: 'emblem:' + t.id, kind: 'emblem', id: t.id, name: titleCase(t.id) + ' EMBLEM', tierId: t.id, unitPrice: t.emblem_price, quantity: 1 })">{{ selected('emblem:' + t.id) ? 'In basket' : '+ Add' }}</EmButton>
              </div>
            </article>
            </div>
            </section>
          </template>
          <template v-else>
            <article v-for="a in sellable" :key="a.ascended_id" class="item-card ascended-offer" :class="{ 'is-off': a.copies <= 0 || fighting(a.ascended_id) || a.sale_value === undefined, selected: selected('sale:' + a.ascended_id) }" :data-sell="a.ascended_id" :style="{ '--tier': 'var(--em-tier-' + a.tier_id + ')' }">
              <div class="item-art"><AscendedPreviewCard v-if="ascendedOf(a.ascended_id)" :ascended="ascendedOf(a.ascended_id)!" :tier-id="a.tier_id" art-slot="preview_card" /><span v-else class="letter">{{ a.name.slice(0, 1) }}</span></div>
              <div class="item-actions offer-details">
                <p class="pack-size">{{ a.copies }} spare {{ a.copies === 1 ? 'copy' : 'copies' }}</p>
                <p v-if="a.sale_value === undefined" class="offer-stock">Sale quote unavailable</p>
                <p v-if="a.sale_value !== undefined" class="item-price em-num"><EmIcon name="coin" />{{ money(a.sale_value) }} <small>each</small></p>
                <div class="selection-slot"><small v-if="selected('sale:' + a.ascended_id)" class="in-basket"><EmIcon name="check" :size="12" />In basket</small></div>
              <EmQuantity v-if="selected('sale:' + a.ascended_id)" :quantity="selected('sale:' + a.ascended_id)!.quantity" :max="available(selected('sale:' + a.ascended_id)!)" :name="selected('sale:' + a.ascended_id)!.name" :disabled="locked || !!selected('sale:' + a.ascended_id)!.requestKey"  @change="setQuantity(selected('sale:' + a.ascended_id)!, $event)" />
              <EmButton v-else data-add :variant="selected('sale:' + a.ascended_id) ? 'primary' : 'secondary'" :disabled="locked || a.copies <= 0 || fighting(a.ascended_id) || a.sale_value === undefined || !!selected('sale:' + a.ascended_id)" @click="add({ key: 'sale:' + a.ascended_id, kind: 'sale', id: a.ascended_id, name: a.name, tierId: a.tier_id, unitPrice: a.sale_value!, quantity: 1 })">{{ selected('sale:' + a.ascended_id) ? 'In basket' : fighting(a.ascended_id) ? 'In active battle' : a.copies <= 0 ? 'No spare copies' : '+ Add' }}</EmButton>
              </div>
            </article>
          </template>
        </div>
        <p v-if="mode === 'buy' ? !visibleOffers.length && !visibleTiers.length : !sellable.length" class="empty">No items match your filters.</p>
        <p v-if="mode === 'buy' && category !== 'emblems' && !visibleOffers.length && !search && !rarity" class="hint">Nothing is on offer right now. EMBLEMs are still available.</p>
        <p class="hint"><EmIcon name="check" />{{ mode === 'buy' ? 'Add several items, then adjust quantities in your basket.' : 'Choose spare copies, then review the batch before selling.' }}</p>
      </div>

      <component :is="portrait ? EmDialog : 'aside'" class="basket-panel" aria-label="Shop basket" :open="basketOpen" :title="mode === 'buy' ? 'Purchase basket' : 'Sale basket'" @close="basketOpen = false">
        <template v-if="portrait && basketOpen">
          <p v-if="message" class="notice" :class="{ interrupted }" role="status"><EmIcon :name="interrupted ? 'warning' : 'check'" />{{ message }}</p>
          <EmNotice v-if="store.error" tone="error">{{ store.error }}</EmNotice>
        </template>
        <header class="basket-head"><EmIcon :name="mode === 'buy' ? 'shop' : 'coin'" :size="25" /><div><h3 class="em-pixel">{{ mode === 'buy' ? 'Purchase basket' : 'Sale basket' }}</h3><p>{{ items.length }} item {{ items.length === 1 ? 'type' : 'types' }} · {{ units }} {{ mode === 'buy' ? 'units' : 'copies' }}</p></div></header>
        <div class="basket-items">
          <p v-if="!items.length" class="basket-empty"><EmIcon name="shop" :size="32" />Your basket is empty.<small>Choose items from the grid to begin.</small></p>
          <article v-for="item in items" :key="item.key" class="basket-item" :data-basket="item.key">
            <EmEmblem v-if="item.kind === 'emblem'" :tier-id="item.id" :size="44" />
            <AscendedPreviewCard v-else-if="ascendedOf(item.id)" class="basket-preview" :ascended="ascendedOf(item.id)!" :tier-id="item.tierId" art-slot="preview_card" />
            <span v-else class="basket-art letter">{{ item.name.slice(0, 1) }}</span>
            <div class="basket-line"><strong>{{ item.name }}</strong><small>{{ money(item.unitPrice) }} {{ item.kind === 'offer' ? '/ pack' : 'each' }}</small></div>
            <button type="button" class="remove" :aria-label="'Remove ' + item.name + ' from basket'" :disabled="locked" @click="remove(item)"><EmIcon name="close" :size="15" /></button>
            <div class="quantity-control"><button type="button" :aria-label="'Decrease ' + item.name + ' quantity'" :disabled="locked || !!item.requestKey || item.quantity <= 1" @click="setQuantity(item, item.quantity - 1)">−</button><input type="number" min="1" :max="Math.max(1, available(item))" :value="item.quantity" :aria-label="item.name + ' quantity'" :disabled="locked || !!item.requestKey" @input="quantityInput(item, $event)" /><button type="button" :aria-label="'Increase ' + item.name + ' quantity'" :disabled="locked || !!item.requestKey || item.quantity >= available(item)" @click="setQuantity(item, item.quantity + 1)">+</button></div>
            <strong class="line-total em-num">{{ money(item.quantity * item.unitPrice) }}</strong>
            <p v-if="problem(item)" class="item-problem">{{ problem(item) }}</p>
            <p v-else-if="item.requestKey && !processing" class="item-problem">Retry this trade before changing its quantity.</p>
          </article>
        </div>
        <footer class="basket-footer">
          <div class="total" data-total><span>{{ mode === 'buy' ? 'Total' : 'You receive' }}</span><strong class="em-num">{{ money(total) }} <small>Insignia</small></strong></div>
          <div class="balance-after" data-balance-after><span>Balance after</span><strong class="em-num">{{ awaitingAcknowledgement ? 'Awaiting confirmation' : money(balanceAfter) }}</strong></div>
          <p v-if="mode === 'buy' && requiredFunds > insignia" class="item-problem">Not enough Insignia. Reduce your quantities.</p>
          <p v-if="mode === 'sell'" class="hint">Only spare copies are sold. Your Ascended stays in your collection.</p>
          <EmButton data-checkout variant="primary" :disabled="!canCheckout" @click="checkout">{{ processing ? 'Processing…' : mode === 'buy' ? 'Buy selected · ' + money(total) : 'Review sale · ' + money(total) }}</EmButton>
        </footer>
      </component>
    </div>
    <button v-if="portrait" type="button" class="basket-toggle" :aria-expanded="basketOpen" @click="basketOpen = true"><EmIcon name="shop" /><span>{{ mode === 'buy' ? 'Purchase basket' : 'Sale basket' }} · {{ units }}</span><strong class="em-num"><EmIcon name="coin" />{{ money(total) }}</strong><EmIcon name="arrow" /></button>
    <EmConfirm :open="reviewOpen" title="Review selected copies" :message="saleReview" :confirm-label="'Sell for ' + money(total) + ' Insignia'" :busy="processing || store.busy" @confirm="trade" @close="reviewOpen = false" />
  </section>
</template>

<style scoped src="./shopPanel.css" />
