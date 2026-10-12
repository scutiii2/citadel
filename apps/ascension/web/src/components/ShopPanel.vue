<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { ShopOffer } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { formatCountdown, titleCase } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import EmButton from "./ui/EmButton.vue";
import EmEmblem from "./ui/EmEmblem.vue";
import EmConfirm from "./ui/EmConfirm.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmPanel from "./ui/EmPanel.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";

/** The Shop tab: the wallet, this account's rotating copy offers (each with limited stock, new
 * ones every few hours), EMBLEMs per tier, and selling one absorbed copy. A card that cannot be
 * bought (sold out, or Insignia would not cover it) is dimmed and does not lift. A copy's price
 * comes from the server, which also refuses when Insignia falls short; the page shows that
 * message (the store's `error`). */
const store = useAscensionStore();
const MAX_QUANTITY = 99;

const insignia = computed(() => store.profile?.insignia ?? 0);
const tiers = computed(() => store.catalog?.tiers ?? []);
const quantities = reactive<Record<string, number>>({});
const message = ref("");
const outOfReach = computed(() => tiers.value.filter((t) => t.emblem_price > insignia.value).map((t) => titleCase(t.id)));

const now = useNowSeconds();
const secondsLeft = computed(() => Math.max(0, store.shopEndsAt - now.value));
const offers = computed(() => store.shop?.offers ?? []);
const nameOf = (id: string) => store.catalog?.ascendeds.find((a) => a.id === id)?.name ?? titleCase(id);
const artOf = (id: string) => spriteFor(store.catalog?.ascendeds.find((a) => a.id === id)?.art, "preview_card");

onMounted(() => void store.loadShop());
// At zero a new rotation has begun: ask for it.
watch(
  () => secondsLeft.value <= 0 && store.shop !== null,
  (over) => {
    if (over) void store.loadShop();
  },
);

function offerOff(offer: ShopOffer): boolean {
  return offer.left <= 0 || offer.price > insignia.value;
}

async function buyOffer(offer: ShopOffer): Promise<void> {
  message.value = "";
  const bought = await store.buyOffer(offer);
  if (bought) {
    const copies = `${bought.copies_granted} ${bought.copies_granted === 1 ? "copy" : "copies"}`;
    message.value = `Bought ${copies} of ${nameOf(bought.ascended_id)} for ${bought.price} Insignia.`;
  }
}

function quantityOf(tierId: string): number {
  return quantities[tierId] ?? 1;
}

function emblemCost(tierId: string, price: number): number {
  return price * quantityOf(tierId);
}

function canBuyEmblems(tierId: string, price: number): boolean {
  const quantity = quantityOf(tierId);
  const valid = Number.isInteger(quantity) && quantity >= 1 && quantity <= MAX_QUANTITY;
  return !store.busy && valid && emblemCost(tierId, price) <= insignia.value;
}

function setQuantity(tierId: string, event: Event): void {
  quantities[tierId] = Number((event.target as HTMLInputElement).value);
}

async function buyEmblems(tierId: string): Promise<void> {
  message.value = "";
  const bought = await store.buyEmblems(tierId, quantityOf(tierId));
  if (bought) {
    message.value = `Bought ${bought.quantity} ${titleCase(bought.tier_id)} EMBLEM${bought.quantity === 1 ? "" : "s"} for ${bought.price} Insignia.`;
  }
}

const sellable = computed(() => (store.profile?.ascendeds ?? []).filter((s) => s.copies > 0));
const selling = ref<string | null>(null);
const sellingName = computed(() => sellable.value.find((s) => s.ascended_id === selling.value)?.name ?? "");

async function sell(): Promise<void> {
  const ascendedId = selling.value;
  selling.value = null;
  if (ascendedId === null) return;
  message.value = "";
  const sale = await store.sellCopy(ascendedId);
  if (sale) {
    message.value = `Sold one copy for ${sale.value} Insignia.`;
  }
}
</script>

<template>
  <section class="shop">
    <p v-if="message" class="notice" role="status"><EmIcon name="check" /> {{ message }}</p>

    <EmPanel class="wallet">
      <div class="balance">
        <p class="em-eyebrow">Your wallet</p>
        <h3 class="em-pixel em-num amount">{{ insignia }} Insignia</h3>
      </div>
      <div v-for="t in tiers" :key="t.id" class="count" :style="{ '--tier': `var(--em-tier-${t.id}, var(--em-tier-common))` }">
        <EmEmblem :tier-id="t.id" :size="36" />
        <strong class="em-pixel em-num">{{ store.profile?.emblems[t.id] ?? 0 }}</strong>
        <span>{{ titleCase(t.id) }} EMBLEMs</span>
      </div>
    </EmPanel>

    <EmPanel>
      <div class="section-head">
        <h3 class="em-pixel">Today's offers</h3>
        <small class="refresh em-num">Refreshes in {{ formatCountdown(secondsLeft) }}</small>
      </div>
      <p v-if="store.shop && offers.length === 0" class="empty">Nothing is on offer right now.</p>
      <ul v-else class="cards">
        <li
          v-for="offer in offers"
          :key="offer.slot"
          class="card em-lift"
          :class="{ 'is-off': offerOff(offer) }"
          :data-offer="offer.slot"
          :style="{ '--tier': `var(--em-tier-${offer.tier_id}, var(--em-tier-common))` }"
        >
          <span v-if="offer.left <= 0" class="ribbon">Sold out</span>
          <div class="portrait">
            <img v-if="artOf(offer.ascended_id)" :src="artOf(offer.ascended_id)!" alt="" draggable="false" />
            <span v-else class="letter" aria-hidden="true">{{ nameOf(offer.ascended_id).slice(0, 1) }}</span>
          </div>
          <h4>{{ nameOf(offer.ascended_id) }}</h4>
          <div class="meta">
            <EmTierBadge :tier-id="offer.tier_id" />
            <span class="em-num">+{{ offer.copies_granted }} {{ offer.copies_granted === 1 ? "copy" : "copies" }}</span>
          </div>
          <p class="em-num owned">{{ offer.owned ? `You have ${offer.owned_copies} spare` : "A new Ascended for you" }}</p>
          <p class="em-num stock">{{ offer.left }} left</p>
          <EmButton variant="primary" class="block" :disabled="store.busy || offerOff(offer)" @click="buyOffer(offer)">
            <EmIcon name="shop" /> {{ offer.price }} Insignia
          </EmButton>
        </li>
      </ul>
      <p class="hint">Offers are yours alone and change every few hours. Spare copies turn into stars, with essence from battles.</p>
    </EmPanel>

    <EmPanel>
      <div class="section-head">
        <h3 class="em-pixel">Buy EMBLEMs</h3>
        <small>Choose how many, then buy</small>
      </div>
      <ul class="cards emblems">
        <li
          v-for="t in tiers"
          :key="t.id"
          class="card em-lift"
          :class="{ 'is-off': t.emblem_price > insignia }"
          :data-tier="t.id"
          :style="{ '--tier': `var(--em-tier-${t.id}, var(--em-tier-common))` }"
        >
          <div class="band" aria-hidden="true" />
          <div class="meta">
            <EmEmblem :tier-id="t.id" :size="56" />
            <EmTierBadge :tier-id="t.id" />
            <span>{{ titleCase(t.id) }} EMBLEM</span>
          </div>
          <p class="em-num price"><strong>{{ t.emblem_price }}</strong> Insignia</p>
          <p class="em-num owned">{{ store.profile?.emblems[t.id] ?? 0 }} owned</p>
          <input
            type="number"
            min="1"
            :max="MAX_QUANTITY"
            :value="quantityOf(t.id)"
            :aria-label="`${titleCase(t.id)} EMBLEMs to buy`"
            @input="setQuantity(t.id, $event)"
          />
          <EmButton variant="primary" class="block" :disabled="!canBuyEmblems(t.id, t.emblem_price)" @click="buyEmblems(t.id)">
            Buy for {{ emblemCost(t.id, t.emblem_price) }}
          </EmButton>
        </li>
      </ul>
      <p v-if="outOfReach.length" class="hint">Not enough Insignia for: {{ outOfReach.join(", ") }}.</p>
    </EmPanel>

    <EmPanel>
      <h3 class="em-pixel">Sell an absorbed copy</h3>
      <p v-if="sellable.length === 0" class="empty">No spare copies to sell.</p>
      <template v-else>
        <p class="hint">Sell one absorbed copy. Your collected Ascended stays with you.</p>
        <ul class="cards sell">
          <li v-for="s in sellable" :key="s.ascended_id" class="card em-lift" :data-sell="s.ascended_id" :style="{ '--tier': `var(--em-tier-${s.tier_id}, var(--em-tier-common))` }">
            <h4>{{ s.name }}</h4>
            <p class="em-num owned">{{ s.copies }} {{ s.copies === 1 ? "copy" : "copies" }} · {{ titleCase(s.tier_id) }}</p>
            <EmButton class="block" :disabled="store.busy" @click="selling = s.ascended_id"><EmIcon name="coin" /> Sell one copy</EmButton>
          </li>
        </ul>
      </template>
    </EmPanel>

    <EmConfirm
      :open="selling !== null"
      title="Sell one copy?"
      :message="`One absorbed copy of ${sellingName} goes back to the shop for Insignia. Its tier can drop.`"
      confirm-label="Sell"
      :busy="store.busy"
      @confirm="sell"
      @close="selling = null"
    />
  </section>
</template>

<style scoped>
.shop {
  display: flex;
  flex-direction: column;
  gap: var(--em-space-5);
}
.notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: 1px solid var(--em-success);
  border-radius: var(--em-radius);
  color: var(--em-success);
  background: var(--em-success-surface);
}
.wallet {
  display: grid;
  grid-template-columns: 1.5fr repeat(6, 1fr);
  gap: var(--em-space-3);
  align-items: center;
}
.amount {
  margin: 6px 0 0;
  font-size: 18px;
}
.count {
  text-align: center;
  font-size: 12px;
  color: var(--tier);
}
.count .em-emblem {
  display: block;
  margin: 0 auto 4px;
}
.count strong {
  display: block;
  margin-bottom: 4px;
  font-size: 22px;
  font-weight: 400;
}
.section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-3);
  margin-bottom: var(--em-space-3);
}
h3 {
  margin: 0 0 var(--em-space-3);
  font-size: 18px;
  line-height: 1.4;
}
.section-head h3 {
  margin: 0;
}
.section-head small {
  color: var(--em-muted);
}
.refresh {
  color: var(--em-accent);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: var(--em-space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--em-space-2);
  padding: var(--em-space-4);
  border: 1px solid var(--em-border);
  border-top: 3px solid var(--tier, var(--em-border));
  border-radius: var(--em-radius);
  background: var(--em-raised);
}
.card.is-off {
  opacity: 0.6;
}
.card h4 {
  margin: 0;
  font-size: 15px;
}
.portrait {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
}
.portrait img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  mix-blend-mode: lighten;
}
.letter {
  font-size: 52px;
  font-weight: 600;
  color: var(--em-accent);
}
.band {
  height: 36px;
  margin: calc(var(--em-space-4) * -1) calc(var(--em-space-4) * -1) 0;
  background: linear-gradient(color-mix(in srgb, var(--tier) 35%, transparent), transparent);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  font-size: 13px;
}
.owned {
  margin: 0;
  font-size: 12px;
  color: var(--em-muted);
}
.stock {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--tier);
}
.price {
  margin: 0;
}
.price strong {
  font-size: 18px;
}
.ribbon {
  position: absolute;
  top: 10px;
  right: -1px;
  padding: 2px 10px;
  background: var(--em-danger-surface);
  border: 1px solid var(--em-danger);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--em-danger);
}
.card input {
  min-height: var(--em-target);
  padding: 8px;
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  color: var(--em-text);
  background: var(--em-bg);
  font: inherit;
  text-align: center;
}
.hint {
  margin: var(--em-space-3) 0 0;
  font-size: 12px;
  color: var(--em-muted);
}
.block {
  width: 100%;
  margin-top: auto;
}
.empty {
  padding: 14px;
  border: 1px dashed var(--em-border);
  font-size: 13px;
  color: var(--em-muted);
}
@media (max-width: 700px) {
  .wallet {
    grid-template-columns: repeat(3, 1fr);
    gap: 20px 10px;
  }
  .balance {
    grid-column: 1 / -1;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--em-divider);
    text-align: center;
  }
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 420px) {
  .cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
