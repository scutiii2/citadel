import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient } from "../api/AscensionClient";
import { CATALOG, PROFILE, ownedAscended, shopOffer, shopWindow } from "../api/AscensionClient.fixtures";
import { ApiError } from "../api/http";
import { useAscensionStore } from "../stores/ascension";
import ShopPanel from "./ShopPanel.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { buyEmblems: vi.fn(), shop: vi.fn(), buyOffer: vi.fn(), sellCopy: vi.fn(), profile: vi.fn() };
  return { useAscensionClient: () => client, newIdempotencyKey: () => crypto.randomUUID() };
});

const client = vi.mocked(useAscensionClient());

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  client.profile.mockResolvedValue(PROFILE);
  client.shop.mockResolvedValue(shopWindow());
});

function mountShop(insignia = 25) {
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = { ...PROFILE, insignia, ascendeds: [{ ...ownedAscended("guardian", { copies: 2 }), sale_value: 12 }] };
  store.shop = shopWindow();
  store.shopEndsAt = Date.now() / 1000 + 3 * 3600 + 12 * 60;
  return { store, wrapper: mount(ShopPanel) };
}

const buyIn = (wrapper: ReturnType<typeof mountShop>["wrapper"], tier: string) => wrapper.find(`[data-tier="${tier}"] button`);

describe("ShopPanel", () => {
  it("keeps Ascended identity on the preview card and only trade details beside it", async () => {
    const { wrapper } = mountShop(500);
    const offer = wrapper.get('[data-offer="0"]');
    expect(offer.get('.offer-details').text()).toContain('1 copy / pack');
    expect(offer.get('.offer-details').text()).toContain('3 left');
    expect(offer.get('.offer-details').text()).not.toContain('Guardian');
    expect(offer.get('.offer-details').find('.em-tier').exists()).toBe(false);
    expect(offer.get('.ascended-name').text()).toBe('Guardian');
    await wrapper.get('[data-mode="sell"]').trigger('click');
    const sale = wrapper.get('[data-sell="guardian"]');
    expect(sale.get('.offer-details').text()).toContain('2 spare copies');
    expect(sale.get('.offer-details').text()).not.toContain('Guardian');
    wrapper.unmount();
  });
  it("keeps search in the mode toolbar and separates All Items into labelled groups", async () => {
    const { wrapper } = mountShop(500);
    expect(wrapper.find('.shop-toolbar input[aria-label="Search shop"]').exists()).toBe(true);
    expect(wrapper.get('section[aria-label="Ascended offers"]').findAll('[data-offer]')).toHaveLength(2);
    expect(wrapper.get('section[aria-label="EMBLEMs"]').findAll('[data-tier]')).toHaveLength(CATALOG.tiers.length);
    await wrapper.get('input[aria-label="Search shop"]').setValue('guardian');
    expect(wrapper.findAll('[data-offer]')).toHaveLength(1);
    expect(wrapper.find('section[aria-label="EMBLEMs"]').exists()).toBe(false);
    await wrapper.get('input[aria-label="Search shop"]').setValue('emblem');
    expect(wrapper.find('section[aria-label="Ascended offers"]').exists()).toBe(false);
    expect(wrapper.findAll('[data-tier]')).toHaveLength(CATALOG.tiers.length);
  });

  it("only offers the rarity filter when selling copies", async () => {
    const { store, wrapper } = mountShop(500);
    expect(wrapper.find('select[aria-label="Filter shop by rarity"]').exists()).toBe(false);
    store.profile!.ascendeds.push({ ...ownedAscended('striker', { tier_id: 'rare', copies: 2 }), sale_value: 20 });
    await wrapper.get('[data-mode="sell"]').trigger('click');
    await wrapper.get('select[aria-label="Filter shop by rarity"]').setValue('rare');
    expect(wrapper.findAll('[data-sell]')).toHaveLength(1);
    expect(wrapper.get('[data-sell]').attributes('data-sell')).toBe('striker');
    await wrapper.get('[data-mode="buy"]').trigger('click');
    expect(wrapper.find('select[aria-label="Filter shop by rarity"]').exists()).toBe(false);
    expect(wrapper.findAll('[data-offer]')).toHaveLength(2);
  });

  it("disables EMBLEMs the Insignia does not cover", async () => {
    const { wrapper } = mountShop(25);

    expect(buyIn(wrapper, "common").attributes("disabled")).toBeUndefined();
    expect(buyIn(wrapper, "rare").attributes("disabled")).toBeDefined();

    await buyIn(wrapper, "common").trigger("click");
    await wrapper.find('[data-basket="emblem:common"] input').setValue("3");

    expect(wrapper.find('[data-total]').text()).toContain("30");
    expect(wrapper.find('[data-checkout]').attributes("disabled")).toBeDefined();
  });

  it("buys EMBLEMs and says what it bought", async () => {
    client.buyEmblems.mockResolvedValue({ kind: "emblems", tier_id: "common", quantity: 2, price: 20 });
    const { wrapper } = mountShop(25);

    await buyIn(wrapper, "common").trigger("click");
    await wrapper.find('[data-basket="emblem:common"] input').setValue("2");
    await wrapper.find('[data-checkout]').trigger("click");
    await flushPromises();

    expect(client.buyEmblems).toHaveBeenCalledExactlyOnceWith("common", 2, expect.any(String));
    expect(wrapper.find(".notice").text()).toContain("Purchased 2 units for 20 Insignia.");
  });

  it("shows the offers with stock, price and the time to the next rotation", () => {
    const { wrapper } = mountShop(500);

    const cards = wrapper.findAll("[data-offer]");
    expect(cards).toHaveLength(2);
    expect(cards[0]!.text()).toContain("Guardian");
    expect(cards[0]!.find("img.portrait").attributes("src")).toBe("/ascended/guardian/sprite_preview_card.webp");
    expect(cards[0]!.find(".tier-frame").attributes("src")).toContain("ascended_card_front_common.webp");
    expect(cards[0]!.text()).toContain("3 left");
    expect(cards[0]!.text()).toContain("40");
    expect(cards[1]!.text()).toContain("1 left");
    expect(wrapper.find(".refresh").text()).toContain("Refreshes in 3:12:");
  });

  it("keeps framed preview cards in both baskets and when selling spare copies", async () => {
    const { wrapper } = mountShop(500);
    await wrapper.get('[data-offer="0"] [data-add]').trigger('click');
    expect(wrapper.get('[data-basket] img.portrait').attributes('src')).toBe('/ascended/guardian/sprite_preview_card.webp');
    await wrapper.get('[data-mode="sell"]').trigger('click');
    expect(wrapper.get('[data-sell="guardian"] img.portrait').attributes('src')).toBe('/ascended/guardian/sprite_preview_card.webp');
    await wrapper.get('[data-sell="guardian"] [data-add]').trigger('click');
    expect(wrapper.get('[data-basket] img.portrait').attributes('src')).toBe('/ascended/guardian/sprite_preview_card.webp');
    wrapper.unmount();
  });

  it("buys an offer and says what it bought", async () => {
    client.buyOffer.mockResolvedValue({ kind: "copies", ascended_id: "guardian", tier_id: "common", copies_granted: 1, price: 40, slot: 0, rotation: 46, left: 2 });
    const { wrapper } = mountShop(500);

    await wrapper.find('[data-offer="0"] button').trigger("click");
    await wrapper.find('[data-checkout]').trigger("click");
    await flushPromises();

    expect(client.buyOffer).toHaveBeenCalledExactlyOnceWith(46, 0, expect.any(String));
    expect(wrapper.find(".notice").text()).toContain("Purchased 1 units for 40 Insignia.");
  });

  it("keeps the server's refusal when an offer costs more than the Insignia", async () => {
    client.buyOffer.mockRejectedValue(new ApiError(409, "that costs 400 Insignia and you have 25"));
    const { store, wrapper } = mountShop(500);

    await wrapper.find('[data-offer="0"] button').trigger("click");
    await wrapper.find('[data-checkout]').trigger("click");
    await flushPromises();

    expect(store.error).toBe("that costs 400 Insignia and you have 25");
  });

  it("marks a sold-out offer and an unaffordable one", async () => {
    const { store, wrapper } = mountShop(50);
    store.shop = shopWindow({ offers: [shopOffer({ left: 0 }), shopOffer({ slot: 1, ascended_id: "scout", price: 90 })] });
    await wrapper.vm.$nextTick();

    const [soldOut, dear] = wrapper.findAll("[data-offer]");
    expect(soldOut!.classes()).toContain("is-off");
    expect(soldOut!.text()).toContain("Sold out");
    expect(soldOut!.find("button").attributes("disabled")).toBeDefined();
    expect(dear!.classes()).toContain("is-off");
    expect(dear!.find("button").attributes("disabled")).toBeDefined();
  });

  it("loads the window when the tab opens", () => {
    mountShop(500);

    expect(client.shop).toHaveBeenCalled();
  });

  it("sells one copy after confirming", async () => {
    client.sellCopy.mockResolvedValue({ kind: "sale", ascended_id: "guardian", value: 12, copies: 1, tier_id: "common" });
    const { wrapper } = mountShop();

    await wrapper.find('[data-mode="sell"]').trigger("click");
    await wrapper.find('[data-sell="guardian"] button').trigger("click");
    await wrapper.find('[data-checkout]').trigger("click");
    expect(client.sellCopy).not.toHaveBeenCalled();
    await wrapper.find("button.confirm").trigger("click");
    await flushPromises();

    expect(client.sellCopy).toHaveBeenCalledExactlyOnceWith("guardian", expect.any(String));
    expect(wrapper.find(".notice").text()).toContain("Sold 1 spare copies for 12 Insignia.");
  });
});
