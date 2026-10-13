import { defineStore } from "pinia";
import { reactive, ref, watch } from "vue";
import { useAscensionStore } from "./ascension";

export type ShopMode = "buy" | "sell";
export type BasketItem = {
  key: string; kind: "offer" | "emblem" | "sale"; id: string; name: string; tierId: string;
  unitPrice: number; quantity: number; rotation?: number; slot?: number; copiesPerPack?: number;
  /** Retain one attempted mutation's key until the server acknowledges it, for safe retries. */
  requestKey?: string;
};

/** Account-scoped selections survive navigation; unfinished trades stay visible on return. */
export const useShopBasketStore = defineStore("shopBasket", () => {
  const game = useAscensionStore();
  const baskets = reactive<{ buy: BasketItem[]; sell: BasketItem[] }>({ buy: [], sell: [] });
  const mode = ref<ShopMode>("buy");
  const processing = ref(false);
  const message = ref("");
  const interrupted = ref(false);
  watch(() => game.profile?.owner, () => {
    baskets.buy = [];
    baskets.sell = [];
    message.value = "";
    mode.value = "buy";
  }, { flush: "sync" });
  return { baskets, mode, processing, message, interrupted };
});
