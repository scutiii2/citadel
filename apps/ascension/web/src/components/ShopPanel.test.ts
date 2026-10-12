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
  return { useAscensionClient: () => client };
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
  store.profile = { ...PROFILE, insignia, ascendeds: [ownedAscended("guardian", { copies: 2 })] };
  store.shop = shopWindow();
  store.shopEndsAt = Date.now() / 1000 + 3 * 3600 + 12 * 60;
  return { store, wrapper: mount(ShopPanel) };
}

const buyIn = (wrapper: ReturnType<typeof mountShop>["wrapper"], tier: string) => wrapper.find(`[data-tier="${tier}"] button`);

describe("ShopPanel", () => {
  it("disables EMBLEMs the Insignia does not cover", async () => {
    const { wrapper } = mountShop(25);

    expect(buyIn(wrapper, "common").attributes("disabled")).toBeUndefined();
    expect(buyIn(wrapper, "rare").attributes("disabled")).toBeDefined();

    await wrapper.find('[data-tier="common"] input').setValue("3");

    expect(buyIn(wrapper, "common").text()).toBe("Buy for 30");
    expect(buyIn(wrapper, "common").attributes("disabled")).toBeDefined();
  });

  it("buys EMBLEMs and says what it bought", async () => {
    client.buyEmblems.mockResolvedValue({ kind: "emblems", tier_id: "common", quantity: 2, price: 20 });
    const { wrapper } = mountShop(25);

    await wrapper.find('[data-tier="common"] input').setValue("2");
    await buyIn(wrapper, "common").trigger("click");
    await flushPromises();

    expect(client.buyEmblems).toHaveBeenCalledExactlyOnceWith("common", 2);
    expect(wrapper.find(".notice").text()).toBe("Bought 2 Common EMBLEMs for 20 Insignia.");
  });

  it("shows the offers with stock, price and the time to the next rotation", () => {
    const { wrapper } = mountShop(500);

    const cards = wrapper.findAll("[data-offer]");
    expect(cards).toHaveLength(2);
    expect(cards[0]!.text()).toContain("Guardian");
    expect(cards[0]!.find("img").attributes("src")).toBe("/ascended/guardian/sprite_preview_card.webp");
    expect(cards[0]!.text()).toContain("3 left");
    expect(cards[0]!.text()).toContain("40");
    expect(cards[1]!.text()).toContain("1 left");
    expect(wrapper.find(".refresh").text()).toContain("Refreshes in 3:12:");
  });

  it("buys an offer and says what it bought", async () => {
    client.buyOffer.mockResolvedValue({ kind: "copies", ascended_id: "guardian", tier_id: "common", copies_granted: 1, price: 40, slot: 0, rotation: 46, left: 2 });
    const { wrapper } = mountShop(500);

    await wrapper.find('[data-offer="0"] button').trigger("click");
    await flushPromises();

    expect(client.buyOffer).toHaveBeenCalledExactlyOnceWith(46, 0);
    expect(wrapper.find(".notice").text()).toBe("Bought 1 copy of Guardian for 40 Insignia.");
  });

  it("keeps the server's refusal when an offer costs more than the Insignia", async () => {
    client.buyOffer.mockRejectedValue(new ApiError(409, "that costs 400 Insignia and you have 25"));
    const { store, wrapper } = mountShop(500);

    await wrapper.find('[data-offer="0"] button').trigger("click");
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

    await wrapper.find('[data-sell="guardian"] button').trigger("click");
    expect(client.sellCopy).not.toHaveBeenCalled();
    await wrapper.find("button.confirm").trigger("click");
    await flushPromises();

    expect(client.sellCopy).toHaveBeenCalledExactlyOnceWith("guardian");
    expect(wrapper.find(".notice").text()).toBe("Sold one copy for 12 Insignia.");
  });
});
