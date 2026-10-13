import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type Profile, type ShopWindow } from "../api/AscensionClient";
import { CATALOG, PROFILE, ownedAscended, shopWindow } from "../api/AscensionClient.fixtures";
import { ApiError } from "../api/http";
import { useAscensionStore } from "../stores/ascension";
import ShopPanel from "./ShopPanel.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { buyEmblems: vi.fn(), shop: vi.fn(), buyOffer: vi.fn(), sellCopy: vi.fn(), profile: vi.fn() };
  return { useAscensionClient: () => client, newIdempotencyKey: () => crypto.randomUUID() };
});
const client = vi.mocked(useAscensionClient());
let profile: Profile;
let window: ShopWindow;
const mounted: ReturnType<typeof mount>[] = [];

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});
beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  profile = { ...PROFILE, insignia: 500, emblems: { common: 2 }, ascendeds: [
    { ...ownedAscended("guardian", { copies: 5 }), sale_value: 12 },
    { ...ownedAscended("striker", { copies: 3 }), sale_value: 20 },
  ] };
  window = shopWindow();
  client.profile.mockImplementation(async () => structuredClone(profile));
  client.shop.mockImplementation(async () => structuredClone(window));
  client.buyEmblems.mockImplementation(async (tier, quantity) => {
    const price = CATALOG.tiers.find(t => t.id === tier)!.emblem_price * quantity;
    profile.insignia -= price;
    profile.emblems[tier] = (profile.emblems[tier] ?? 0) + quantity;
    return { kind: "emblems", tier_id: tier, quantity, price };
  });
  client.buyOffer.mockImplementation(async (rotation, slot) => {
    const offer = window.offers.find(o => o.slot === slot)!;
    profile.insignia -= offer.price;
    offer.left -= 1;
    return { kind: "copies", ascended_id: offer.ascended_id, tier_id: offer.tier_id, copies_granted: offer.copies_granted, price: offer.price, rotation, slot, left: offer.left };
  });
  client.sellCopy.mockImplementation(async id => {
    const owned = profile.ascendeds.find(a => a.ascended_id === id)!;
    const value = owned.sale_value!;
    profile.insignia += value;
    owned.copies -= 1;
    return { kind: "sale", ascended_id: id, value, copies: owned.copies, tier_id: owned.tier_id };
  });
});
afterEach(() => { mounted.splice(0).forEach(w => w.unmount()); });
async function setup() {
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = structuredClone(profile);
  const wrapper = mount(ShopPanel);
  mounted.push(wrapper);
  await flushPromises();
  return { store, wrapper };
}

describe("shop basket", () => {
  it("buys multiple offer packs and emblem quantities together with an accurate total", async () => {
    const { wrapper } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    await wrapper.get('[data-tier="common"] button[data-add]').trigger("click");
    await wrapper.get('[data-basket="offer:46:0"] input').setValue(2);
    await wrapper.get('[data-basket="emblem:common"] input').setValue(3);
    expect(wrapper.get('[data-total]').text()).toContain("110");
    expect(wrapper.get('[data-balance-after]').text()).toContain("390");
    expect(client.buyOffer).not.toHaveBeenCalled();
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    expect(client.buyOffer).toHaveBeenCalledTimes(2);
    expect(client.buyEmblems).toHaveBeenCalledExactlyOnceWith("common", 3, expect.any(String));
    expect(wrapper.findAll('[data-basket]')).toHaveLength(0);
    expect(wrapper.get('[role="status"]').text()).toContain("110");
  });

  it("limits quantities to stock and prevents overspending", async () => {
    profile.insignia = 50;
    const { wrapper } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    const quantity = wrapper.get('[data-basket="offer:46:0"] input');
    await quantity.setValue(99);
    expect((quantity.element as HTMLInputElement).value).toBe("3");
    expect(wrapper.get('[data-checkout]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Not enough Insignia");
    await quantity.setValue(1);
    expect(wrapper.get('[data-checkout]').attributes("disabled")).toBeUndefined();
  });

  it("reviews a multi-character spare-copy sale before sending any mutations", async () => {
    const { wrapper } = await setup();
    await wrapper.get('[data-mode="sell"]').trigger("click");
    await wrapper.get('[data-sell="guardian"] button[data-add]').trigger("click");
    await wrapper.get('[data-sell="striker"] button[data-add]').trigger("click");
    await wrapper.get('[data-basket="sale:guardian"] input').setValue(2);
    await wrapper.get('[data-basket="sale:striker"] input').setValue(3);
    expect(wrapper.get('[data-total]').text()).toContain("84");
    await wrapper.get('[data-checkout]').trigger("click");
    expect(client.sellCopy).not.toHaveBeenCalled();
    expect(wrapper.get('dialog').text()).toContain("Guardian");
    await wrapper.get('button.confirm').trigger("click");
    await flushPromises();
    expect(client.sellCopy).toHaveBeenCalledTimes(5);
    expect(profile.ascendeds.map(a => a.copies)).toEqual([3, 0]);
    expect(profile.insignia).toBe(584);
  });

  it("removes completed units but retains failed and unprocessed units", async () => {
    const { wrapper, store } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    await wrapper.get('[data-basket="offer:46:0"] input').setValue(2);
    await wrapper.get('[data-tier="common"] button[data-add]').trigger("click");
    const success = client.buyOffer.getMockImplementation()!;
    client.buyOffer.mockImplementationOnce(success).mockRejectedValueOnce(new ApiError(409, "Sold out"));
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    expect(client.buyOffer).toHaveBeenCalledTimes(2);
    expect(client.buyEmblems).not.toHaveBeenCalled();
    expect((wrapper.get('[data-basket="offer:46:0"] input').element as HTMLInputElement).value).toBe("1");
    expect(wrapper.find('[data-basket="emblem:common"]').exists()).toBe(true);
    expect(store.error).toBe("Sold out");
    expect(wrapper.get('[role="status"]').text()).toContain("1");
  });

  it("keeps separate buy and sell selections when switching modes", async () => {
    const { wrapper } = await setup();
    await wrapper.get('[data-tier="common"] button[data-add]').trigger("click");
    await wrapper.get('[data-mode="sell"]').trigger("click");
    expect(wrapper.findAll('[data-basket]')).toHaveLength(0);
    await wrapper.get('[data-sell="guardian"] button[data-add]').trigger("click");
    await wrapper.get('[data-mode="buy"]').trigger("click");
    expect(wrapper.find('[data-basket="emblem:common"]').exists()).toBe(true);
    expect(wrapper.find('[data-basket="sale:guardian"]').exists()).toBe(false);
  });

  it("requires expired offers to be removed before checkout", async () => {
    const { wrapper, store } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    store.shop = { ...window, rotation: 47 };
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[data-checkout]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-basket="offer:46:0"]').text()).toContain("Expired offer");
    expect(client.buyOffer).not.toHaveBeenCalled();
  });

  it("keeps a changed quote for review rather than silently spending more", async () => {
    const { wrapper, store } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    store.shop!.offers[0]!.price = 70;
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[data-checkout]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-basket="offer:46:0"]').text()).toContain("Price changed");
  });

  it("locks sales for the fighter in an active battle and never sells an emblem", async () => {
    const { wrapper, store } = await setup();
    store.profile!.active_battle = "b1";
    await wrapper.get('[data-mode="sell"]').trigger("click");
    expect(wrapper.get('[data-sell="guardian"] button[data-add]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-tier]').exists()).toBe(false);
  });

  it("clears basket selections on an account change", async () => {
    const { wrapper, store } = await setup();
    await wrapper.get('[data-tier="common"] button[data-add]').trigger("click");
    store.profile = { ...profile, owner: "different" };
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll('[data-basket]')).toHaveLength(0);
  });

  it("preserves unprocessed items after navigating away during a batch", async () => {
    const { wrapper } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    await wrapper.get('[data-basket="offer:46:0"] input').setValue(2);
    await wrapper.get('[data-tier="common"] button[data-add]').trigger("click");
    const complete = client.buyOffer.getMockImplementation()!;
    let settle!: () => void;
    client.buyOffer.mockImplementationOnce((rotation, slot) => new Promise(resolve => { settle = async () => resolve(await complete(rotation, slot)); }));
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    wrapper.unmount();
    settle();
    await flushPromises();
    const returned = mount(ShopPanel);
    mounted.push(returned);
    await flushPromises();
    expect(client.buyOffer).toHaveBeenCalledTimes(1);
    expect((returned.get('[data-basket="offer:46:0"] input').element as HTMLInputElement).value).toBe("1");
    expect(returned.find('[data-basket="emblem:common"]').exists()).toBe(true);
    expect(returned.get('[role="status"]').text()).toContain("Remaining items");
  });

  it("reuses the failed operation's idempotency key when a user retries", async () => {
    const { wrapper } = await setup();
    await wrapper.get('[data-tier="common"] button[data-add]').trigger("click");
    client.buyEmblems.mockRejectedValueOnce(new ApiError(503, "Connection interrupted"));
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    const firstKey = client.buyEmblems.mock.calls[0]![2];
    expect(wrapper.get('[data-basket="emblem:common"] input').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    expect(client.buyEmblems.mock.calls[1]![2]).toBe(firstKey);
    expect(profile.insignia).toBe(490);
    expect(wrapper.findAll('[data-basket]')).toHaveLength(0);
  });

  it("reconciles a committed purchase with a lost response using its original rotation", async () => {
    profile.insignia = 40;
    window.offers[0]!.left = 1;
    const { wrapper, store } = await setup();
    await wrapper.get('[data-offer="0"] button[data-add]').trigger("click");
    const buy = client.buyOffer.getMockImplementation()!;
    let committed!: Awaited<ReturnType<typeof buy>>;
    client.buyOffer.mockImplementationOnce(async (rotation, slot, key) => {
      committed = await buy(rotation, slot, key);
      throw new ApiError(503, "Response lost");
    });
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    const firstKey = client.buyOffer.mock.calls[0]![2];
    expect(window.offers[0]!.left).toBe(0);
    store.shop!.rotation = 47;
    store.profile!.insignia = 0;
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[data-checkout]').attributes("disabled")).toBeUndefined();
    client.buyOffer.mockImplementationOnce(async (rotation, slot, key) => {
      expect([rotation, slot, key]).toEqual([46, 0, firstKey]);
      return committed;
    });
    await wrapper.get('[data-checkout]').trigger("click");
    await flushPromises();
    expect(profile.insignia).toBe(0);
    expect(wrapper.findAll('[data-basket]')).toHaveLength(0);
  });
});
