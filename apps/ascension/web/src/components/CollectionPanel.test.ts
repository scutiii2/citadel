import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type Profile } from "../api/AscensionClient";
import { CATALOG, PROFILE, ownedAscended, ascendedInfo } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "../stores/ascension";
import CollectionPanel from "./CollectionPanel.vue";
import PresetEditor from "./PresetEditor.vue";
import TreeTab from "./TreeTab.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { tree: vi.fn(), setDefaultPreset: vi.fn(), putSquad: vi.fn(), personalities: vi.fn(), preset: vi.fn(), savePreset: vi.fn(), profile: vi.fn(), addStar: vi.fn(), raiseTier: vi.fn() };
  return { useAscensionClient: () => client };
});

const client = vi.mocked(useAscensionClient());

async function progression(wrapper: ReturnType<typeof mountPanel>) {
  await wrapper.get('[role="tab"][aria-label="Progression"]').trigger('click');
}

it('uses a dedicated Progression tab and places readiness directly under the name', async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended('guardian', { copies: 2 })] });
  await wrapper.find('.ascended-card').trigger('click');
  await flushPromises();
  const header = wrapper.get('.ascended-details .head');
  expect(header.find('.battle-status').text()).toBe('Ready for battle');
  expect(header.find('.copy-summary').exists()).toBe(false);
  expect(wrapper.find('.progression-drawer').exists()).toBe(false);
  expect(wrapper.find('.progression-panel').exists()).toBe(false);
  await progression(wrapper);
  expect(wrapper.get('[role=tabpanel][aria-label=Progression]').text()).toContain('Spare copies');
  expect(wrapper.find('.overview').exists()).toBe(false);
  await wrapper.get('[role=tab][aria-label="Overview"]').trigger('click');
  expect(wrapper.find('.overview-loadout').exists()).toBe(true);
});

it('shows fainted status in the header and capped XP without an upgrade button', async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended('guardian', { stars_needed: null, next_tier_id: null, level: 30, xp_needed: null, faint_until: Date.now() / 1000 + 120 })] });
  await wrapper.find('.ascended-card').trigger('click');
  await flushPromises();
  expect(wrapper.get('.ascended-details .head .battle-status').text()).toContain('Fainted, ready in');
  await progression(wrapper);
  expect(wrapper.get('.progression-side').text()).toContain('Highest level reached');
  expect(wrapper.find('.upgrade button').exists()).toBe(false);
});

it("shows matching essence art in the collection and detail costs", async () => {
  const wrapper = mountPanel({ ...PROFILE, essences: { rare: 7 }, ascendeds: [ownedAscended("guardian", { tier_id: "rare" })] });
  expect(wrapper.find(".essences img.em-essence").attributes("src")).toContain("essence_rare.webp");
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  await progression(wrapper);
  expect(wrapper.findAll(".progression-panel img.em-essence")).toHaveLength(2);
  expect(wrapper.findAll(".progression-panel img.em-essence").every(img => img.attributes("src")?.includes("essence_rare.webp"))).toBe(true);
});

it.each([['legendary', 20], ['forbidden', 50]] as const)("shows %s stars as a capped upgrade without a tier target", async (tier, cap) => {
  const wrapper = mountPanel({ ...PROFILE, essences: { [tier]: 10 }, ascendeds: [ownedAscended("guardian", {
    tier_id: tier, stars: cap, stars_needed: cap, next_tier_id: null, can_star_up: false, can_tier_up: false,
  })] });
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  await progression(wrapper);
  const panel = wrapper.find(".progression-panel");
  expect(panel.text()).toContain(`Stars ${cap} / ${cap}`);
  expect(panel.text()).toContain("Maximum stars reached");
  expect(panel.text()).not.toContain("to reach");
  expect(panel.text()).not.toContain("Raise to");
});

it("opens the details when a collected card is pressed", async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
  expect(wrapper.find(".ascended-details").attributes("open")).toBeUndefined();
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  expect(wrapper.find(".details .detail-portrait").attributes("src")).toBe("/ascended/guardian/sprite_main_card.webp");
  await progression(wrapper);
  expect(wrapper.find(".progression-panel").text()).toContain("A star costs");
});

it("filters collected cards by search and rarity and can hide concealed cards", async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian"), ownedAscended("striker", { tier_id: "rare" })] });
  await wrapper.find('input[type="search"]').setValue("str");
  expect(wrapper.findAll(".ascended-card")).toHaveLength(1);
  await wrapper.find('[data-tier-filter="common"]').trigger("click");
  expect(wrapper.findAll(".ascended-card")).toHaveLength(0);
  await wrapper.find('input[aria-label="Show uncollected"]').setValue(false);
  expect(wrapper.findAll(".missing-ascended")).toHaveLength(0);
});

// jsdom has no <dialog> methods.
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
  client.personalities.mockResolvedValue({ items: [], next_cursor: null });
  client.preset.mockResolvedValue({ ascended_id: "guardian", slot: 1, instance_ids: [] });
  client.tree.mockResolvedValue({ ascended_id: "guardian", level: 1, essences: {}, nodes: [], slots: [], loadout: {} });
});

function mountPanel(profile: Profile = PROFILE) {
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = profile;
  return mount(CollectionPanel);
}

it("uses main card art and persists the Overview battle default with its three-personality preview", async () => {
  client.preset.mockImplementation(async (_id, slot) => ({ ascended_id: "guardian", slot, instance_ids: slot === 3 ? ["outside-page"] : [], personalities: slot === 3 ? [{ id: "outside-page", type: "BOLD", tier: 2 }] : [] }));
  client.setDefaultPreset.mockResolvedValue({ ascended_id: "guardian", slot: 3 });
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  expect(wrapper.find(".detail-portrait").attributes("src")).toBe("/ascended/guardian/sprite_main_card.webp");
  expect(wrapper.findAll(".overview-loadout .ability-slot")).toHaveLength(6);
  await wrapper.get('button[aria-label="Use preset 3 as battle default"]').trigger("click");
  await flushPromises();
  expect(client.setDefaultPreset).toHaveBeenCalledWith("guardian", 3);
  expect(wrapper.find(".preset-preview").text()).toContain("Bold");
  expect(wrapper.findAll(".preset-preview li")).toHaveLength(3);
  expect(useAscensionStore().profile!.ascendeds[0]!.default_preset_slot).toBe(3);
});

it("ignores an initial Overview response delivered after a newer tree snapshot", async () => {
  let finish!: (tree: any) => void;
  client.tree.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
  await wrapper.get(".ascended-card").trigger("click");
  await flushPromises();
  await wrapper.findAll('[role="tab"]').find(tab => tab.text() === "Ability tree")!.trigger("click");
  await flushPromises();
  const fresh = { ascended_id: "guardian", level: 1, essences: {}, slots: [{ id: "a1", kind: "ability", branches: null }], loadout: { a1: "fresh" }, nodes: [{ id: "fresh", name: "Fresh ability", kind: "ability", x: 0, y: 0, requires: [], unlock_level: 1, root: true, cost: null, state: "learned", reason: null }] };
  wrapper.getComponent(TreeTab).vm.$emit("loaded", fresh);
  finish({ ascended_id: "guardian", level: 1, essences: {}, nodes: [], slots: [], loadout: {} });
  await flushPromises();
  await wrapper.findAll('[role="tab"]').find(tab => tab.text() === "Overview")!.trigger("click");
  expect(wrapper.find('.overview-loadout button[aria-label="A1: Fresh ability"]').exists()).toBe(true);
});

describe("CollectionPanel", () => {
  it("shows a card per owned Ascended and lists the others as not collected", () => {
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian", { copies: 3, tier_id: "rare" })] });

    const cards = wrapper.findAll(".ascended-card");
    expect(cards).toHaveLength(1);
    expect(cards[0]!.find(".em-tier").exists()).toBe(false);
    expect(cards[0]!.text()).not.toMatch(/copies|XP/);
    expect(cards[0]!.find(".stars").text()).toBe("★ 0");
    expect(cards[0]!.find(".ascended-name").text()).toBe("Guardian");
    expect(cards[0]!.find(".level").text()).toBe("Lv 3");
    expect(cards[0]!.find("img.portrait").attributes("src")).toContain("sprite_battle.webp");
    expect(cards[0]!.find(".passive").exists()).toBe(false);
    expect(wrapper.findAll(".missing-ascended")).toHaveLength(3);
  });

  it("counts a faint down", () => {
    const wrapper = mountPanel({
      ...PROFILE,
      ascendeds: [ownedAscended("guardian", { xp_needed: null, faint_until: Date.now() / 1000 + 65 })],
    });

    const text = wrapper.find(".ascended-card").text();
    expect(text).toMatch(/Fainted, ready in 1:0[56]/);
    expect(wrapper.find(".ascended-card").classes()).toContain("down");
  });

  it("opens an Ascended's abilities, personalities (paged) and presets", async () => {
    client.personalities.mockResolvedValueOnce({ items: [{ id: "p1", type: "AGGRESSIVE", tier: 2 }], next_cursor: 7 });
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });

    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();

    expect(client.personalities).toHaveBeenCalledWith("guardian", null, 50);
    expect(client.preset).toHaveBeenCalledWith("guardian", 1);
    const details = wrapper.find(".details");
    expect(details.find(".big-card").exists()).toBe(false);
    await progression(wrapper);
    expect(details.find(".foundation-summary").exists()).toBe(false);
    await wrapper.findAll('[role="tab"]').find((b) => b.text() === "Personalities")!.trigger("click");
    expect(details.find(".personalities").text()).toContain("Aggressive");
    expect(details.find(".personalities").text()).toContain("Tier 2");
    expect(details.text()).toContain("1+ collected");

    client.personalities.mockResolvedValueOnce({ items: [{ id: "p2", type: "CAUTIOUS", tier: 1 }], next_cursor: null });
    await details.findAll("button").find((b) => b.text() === "Show more")!.trigger("click");
    await flushPromises();

    expect(client.personalities).toHaveBeenLastCalledWith("guardian", 7, 50);
    expect(wrapper.find(".personalities").text()).toContain("Cautious");
    expect(wrapper.find(".details").findAll("button").some((b) => b.text() === "Show more")).toBe(false);
  });
});

it("shows copies inside Progression at the top tier and readiness across tabs", async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian", { copies: 0, stars_needed: null })] });
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  await progression(wrapper);
  expect(wrapper.find(".progression-resources").text()).toContain("Spare copies0");
  await wrapper.findAll('[role="tab"]').find((b) => b.text() === "Personalities")!.trigger("click");
  expect(wrapper.get(".ascended-details .head .battle-status").text()).toBe("Ready for battle");
});

it("explains a personality beside its preset control", async () => {
  client.personalities.mockResolvedValue({ items: [{ id: "p1", type: "AGGRESSIVE", tier: 2 }], next_cursor: null });
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  await wrapper.findAll('[role="tab"]').find((b) => b.text() === "Personalities")!.trigger("click");
  expect(wrapper.find(".personality-description").text()).toContain("2 preference weight");
});

it("updates the summary when learning an ability refreshes the profile", async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
  await wrapper.find(".ascended-card").trigger("click");
  await flushPromises();
  useAscensionStore().profile = { ...PROFILE, ascendeds: [ownedAscended("guardian", { copies: 4, can_star_up: false })] };
  await flushPromises();
  await progression(wrapper);
  expect(wrapper.find(".progression-resources").text()).toContain("Spare copies4");
});

describe("stars and tiers", () => {
  const ready = (extra = {}) => ownedAscended("guardian", { copies: 2, stars: 0, stars_needed: 2, star_essence_cost: 2, next_tier_id: "unique", tier_id: "rare", can_star_up: true, ...extra });

  it("lists the essence held above the cards", () => {
    const wrapper = mountPanel({ ...PROFILE, essences: { common: 3, rare: 0, royal: 1 } });

    expect(wrapper.findAll(".essences li").map((li) => li.text())).toEqual(["Common essence 3", "Royal essence 1"]);
  });

  it("adds a star with a spare copy and essence, then shows the refreshed stars", async () => {
    client.addStar.mockResolvedValue({ kind: "star", ascended_id: "guardian", tier_id: "rare", stars: 1, stars_needed: 2, essence_spent: 2, copies: 1, can_tier_up: false });
    client.profile.mockResolvedValue({ ...PROFILE, essences: { rare: 1 }, ascendeds: [ready({ copies: 1, stars: 1, can_star_up: false })] });
    const wrapper = mountPanel({ ...PROFILE, essences: { rare: 3 }, ascendeds: [ready()] });

    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();
    await progression(wrapper);
    const upgrade = wrapper.find(".upgrade");
    expect(upgrade.text()).toContain("Stars 0 / 2 to reach Unique");
    expect(upgrade.text()).toContain("1 spare copy");
    expect(upgrade.text()).toContain("2 Rare essence");
    expect(upgrade.findAll(".star-cost li")).toHaveLength(2);
    await upgrade.findAll("button").find((b) => b.text() === "Add a star")!.trigger("click");
    await flushPromises();

    expect(client.addStar).toHaveBeenCalledWith("guardian");
    expect(wrapper.find(".upgrade").text()).toContain("Stars 1 / 2 to reach Unique");
    expect(wrapper.find(".upgrade-note").text()).toBe("Guardian gained a star: 1 of 2.");
    expect(wrapper.find(".upgrade").findAll("button").find((b) => b.text() === "Add a star")!.attributes("disabled")).toBeDefined();
  });

  it("offers the tier instead of a star once the stars are full", async () => {
    client.raiseTier.mockResolvedValue({ kind: "tier", ascended_id: "guardian", from_tier_id: "rare", tier_id: "unique", stars: 0 });
    client.profile.mockResolvedValue({ ...PROFILE, ascendeds: [ready({ tier_id: "unique", stars: 0, stars_needed: 3, next_tier_id: "royal", can_star_up: false })] });
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ready({ stars: 2, can_star_up: false, can_tier_up: true })] });

    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();
    await progression(wrapper);
    const buttons = wrapper.find(".upgrade").findAll("button").map((b) => b.text());
    expect(buttons).toEqual(["Raise to Unique"]);
    await wrapper.find(".upgrade button").trigger("click");
    await flushPromises();

    expect(client.raiseTier).toHaveBeenCalledWith("guardian");
    expect(wrapper.find(".upgrade-note").text()).toBe("Guardian rose to Unique.");
    expect(wrapper.find(".details .em-tier").text()).toBe("Unique");
  });

  it("disables the star when a copy or essence is missing, and says the top of the ladder has none", async () => {
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ready({ can_star_up: false }), ownedAscended("cindrax", { tier_id: "forbidden", stars_needed: null, next_tier_id: null })] });

    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();
    await progression(wrapper);
    expect(wrapper.find(".upgrade button").attributes("disabled")).toBeDefined();
    await wrapper.findAll(".ascended-card")[1]!.trigger("click");
    await flushPromises();
    await progression(wrapper);
    expect(wrapper.find(".upgrade").text()).toContain("Top of its ladder");
    expect(wrapper.find(".upgrade button").exists()).toBe(false);
  });
});

describe("not collected", () => {
  it("lets owned and not collected cards lift on hover, but not a fainted one", () => {
    const wrapper = mountPanel({
      ...PROFILE,
      ascendeds: [ownedAscended("guardian"), ownedAscended("striker", { faint_until: Date.now() / 1000 + 600 })],
    });

    const [ready, fainted] = wrapper.findAll(".ascended-card .face");
    expect(ready!.classes()).toContain("preview-lift");
    expect(fainted!.classes()).not.toContain("preview-lift");
    expect(wrapper.find(".missing-ascended .card").classes()).toContain("preview-lift");
  });

  it("marks a fainted Ascended in the squad and the collected grid without opening it", () => {
    const wrapper = mountPanel({
      ...PROFILE,
      squad: ["guardian"],
      ascendeds: [ownedAscended("guardian", { in_squad: true, faint_until: Date.now() / 1000 + 600 }), ownedAscended("striker", { faint_until: Date.now() / 1000 + 600 })],
    });

    expect(wrapper.find(".squad-card.down .squad-fainted").text()).toContain("Fainted");
    expect(wrapper.find(".ascended-card .ko-badge").text()).toContain("Fainted");
  });

  it("shows only a face-down card for each Ascended not collected yet", () => {
    const wrapper = mountPanel();

    const rows = wrapper.findAll(".missing-ascended");
    expect(rows[0]!.find(".card.flipped").exists()).toBe(true);
    expect(rows[0]!.text()).not.toContain("Striker");
  });
});

describe("PresetEditor", () => {
  const items = ["p1", "p2", "p3", "p4"].map((id) => ({ id, type: "BOLD", tier: 1 }));

  it("shows the selected personalities and unsaved state in its preset inspector", async () => {
    const wrapper = mount(PresetEditor, { props: { ascendedId: "guardian", ascendedName: "Guardian", personalities: items } });
    await flushPromises();
    await wrapper.findAll("input[role='switch']")[0]!.setValue(true);
    expect(wrapper.find('[aria-label="Personality preset"]').text()).toContain("Bold");
    expect(wrapper.find('[role="status"]').text()).toContain("Unsaved changes");
  });

  it("equips at most three personalities and saves the preset", async () => {
    client.preset.mockResolvedValue({ ascended_id: "guardian", slot: 1, instance_ids: ["p1"] });
    client.savePreset.mockResolvedValue({ ascended_id: "guardian", slot: 1, instance_ids: ["p1", "p2", "p3"] });
    const wrapper = mount(PresetEditor, { props: { ascendedId: "guardian", ascendedName: "Guardian", personalities: items } });
    await flushPromises();

    const switches = wrapper.findAll("input[role='switch']");
    expect(switches.map((s) => (s.element as HTMLInputElement).checked)).toEqual([true, false, false, false]);
    await switches[1]!.setValue(true);
    await switches[2]!.setValue(true);
    expect((switches[3]!.element as HTMLInputElement).disabled).toBe(true);

    await wrapper.findAll("button").find((b) => b.text() === "Save preset")!.trigger("click");
    await flushPromises();

    expect(client.savePreset).toHaveBeenCalledExactlyOnceWith("guardian", 1, ["p1", "p2", "p3"]);
  });

  it("announces the save in a toast and keeps the saved state", async () => {
    client.preset.mockResolvedValue({ ascended_id: "guardian", slot: 1, instance_ids: [] });
    client.savePreset.mockResolvedValue({ ascended_id: "guardian", slot: 1, instance_ids: ["p1"] });
    const wrapper = mount(PresetEditor, { props: { ascendedId: "guardian", ascendedName: "Guardian", personalities: items } });
    await flushPromises();

    await wrapper.findAll("input[role='switch']")[0]!.setValue(true);
    expect(wrapper.find(".count").text()).toBe("Preset 1 · 1 of 3 personalities equipped");
    await wrapper.find("button.save").trigger("click");
    await flushPromises();

    expect(wrapper.find(".em-toast").text()).toBe("Preset 1 saved. Guardian is ready.");
    expect((wrapper.find("button.save").element as HTMLButtonElement).disabled).toBe(true);
  });

  it("loads the slot the user picks", async () => {
    const wrapper = mount(PresetEditor, { props: { ascendedId: "guardian", ascendedName: "Guardian", personalities: items } });
    await flushPromises();

    await wrapper.findAll("[role=tab]").find((b) => b.text() === "3")!.trigger("click");
    await flushPromises();

    expect(client.preset).toHaveBeenLastCalledWith("guardian", 3);
  });

  describe("Ascension Types", () => {
    const TYPED = {
      ...CATALOG,
      ascendeds: [
        ascendedInfo("guardian", { starter: true, ascension_types: ["enchant"] }),
        ascendedInfo("striker", { starter: true, ascension_types: ["divine", "enchant"] }),
        ascendedInfo("bruiser", { ascension_types: [] }),
        ascendedInfo("cindrax", { forbidden: true, ascension_types: ["abyss"] }),
      ],
    };
    const PROFILE_TYPED: Profile = {
      ...PROFILE,
      ascendeds: [
        ownedAscended("guardian", { ascension_types: ["enchant"] }),
        ownedAscended("striker", { ascension_types: ["divine", "enchant"] }),
        ownedAscended("bruiser", { ascension_types: [] }),
      ],
    };

    function mountTyped() {
      const wrapper = mountPanel(PROFILE_TYPED);
      useAscensionStore().catalog = TYPED;
      return wrapper;
    }
    const chip = (wrapper: ReturnType<typeof mountTyped>, label: string) => wrapper.findAll(".type-filters .chip").find((c) => c.text() === label)!;
    const names = (wrapper: ReturnType<typeof mountTyped>) => wrapper.findAll(".ascended-card .ascended-name").map((n) => n.text());

    it("offers all type toggles with no filters selected", async () => {
      const wrapper = mountTyped();
      await flushPromises();
      expect(wrapper.findAll(".type-filters .chip").map((c) => c.text())).toEqual(["Pure", "Abyss", "Divine", "Crimson", "Enchant", "Synthetic"]);
      expect(wrapper.findAll(".type-filters .chip").every(c => c.attributes("aria-pressed") === "false")).toBe(true);
      expect(names(wrapper)).toEqual(["Guardian", "Striker", "Bruiser"]);
    });

    it("combines type toggles and clears a filter on a second click", async () => {
      const wrapper = mountTyped();
      await chip(wrapper, "Enchant").trigger("click");
      expect(names(wrapper)).toEqual(["Guardian", "Striker"]);
      expect(wrapper.findAll(".missing-ascended")).toHaveLength(0);
      await chip(wrapper, "Enchant").trigger("click");
      await chip(wrapper, "Abyss").trigger("click");
      expect(wrapper.find(".empty").text()).toBe("No Ascended match your filters.");
      expect(wrapper.findAll(".missing-ascended")).toHaveLength(1);
      await chip(wrapper, "Abyss").trigger("click");
      expect(wrapper.findAll(".type-filters .chip").every(c => c.attributes("aria-pressed") === "false")).toBe(true);
    });

    it("groups owned cards by type when its radio is selected", async () => {
      const wrapper = mountTyped();
      await wrapper.find('input[name="collection-grouping"][value="type"]').setValue();
      const groups = wrapper.findAll(".group").map((g) => [g.find(".group-name").text(), g.findAll(".ascended-name").map((n) => n.text())]);
      expect(groups).toEqual([
        ["Divine 1", ["Striker"]],
        ["Enchant 2", ["Guardian", "Striker"]],
        ["No type 1", ["Bruiser"]],
      ]);
    });
  });
});


describe("collection squad controls", () => {
  it("replaces a full squad slot by dragging a collected card", async () => {
    const wrapper = mountPanel({ ...PROFILE, squad_size: 1, ascendeds: [ownedAscended("guardian", { in_squad: true }), ownedAscended("striker")] });
    client.putSquad.mockResolvedValue({ ascended_ids: ["striker"], size: 1 });
    client.profile.mockResolvedValue({ ...PROFILE, squad: ["striker"], ascendeds: [ownedAscended("guardian"), ownedAscended("striker", { in_squad: true })] });
    await wrapper.find(".owned-entry").trigger("dragstart");
    await wrapper.find(".squad-slot").trigger("drop");
    await flushPromises();
    expect(client.putSquad).toHaveBeenCalledWith(["striker"]);
  });

  it("retains the selection when closing details and supports keyboard selection", async () => {
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
    await wrapper.find(".ascended-card").trigger("keydown", { key: "Enter" });
    await flushPromises();
    await wrapper.find('.ascended-details button[aria-label="Close"]').trigger("click");
    expect(wrapper.find(".ascended-card").attributes("aria-pressed")).toBe("true");
  });

  it("uses main card art in Overview independently of battle art", async () => {
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian")] });
    useAscensionStore().catalog = { ...CATALOG, ascendeds: [ascendedInfo("guardian", { art: { main_card: "/legacy-main.webp", preview_card: "/legacy-preview.webp", battle: null, focus: 50, focus_preview: 50, animation: null } })] };
    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();
    expect(wrapper.find(".detail-portrait").attributes("src")).toBe("/legacy-main.webp");
  });
  it("renders the configured slots, marks members and lets the last one be removed", async () => {
    const wrapper = mountPanel({ ...PROFILE, squad_size: 3 });
    expect(wrapper.findAll(".squad-slot")).toHaveLength(3);
    expect(wrapper.findAll(".squad-empty")).toHaveLength(2);
    expect(wrapper.find(".squad-strip .squad-slot button").exists()).toBe(false);
    expect(wrapper.find(".squad-help [role=tooltip]").text()).toContain("Drag an Ascended");
    expect(wrapper.find(".owned-entry").exists()).toBe(false);
    expect(wrapper.find(".empty").text()).toBe("Everyone you collected is in your squad.");
    await wrapper.find(".squad-card").trigger("click");
    await flushPromises();
    expect(wrapper.find(".squad-control button").text()).toBe("Remove from squad");
    expect(wrapper.find(".squad-control button").attributes("disabled")).toBeUndefined();
    expect(wrapper.find(".squad-control").text()).not.toContain("Keep at least one");
  });

  it("adds an outsider and removes a member through the store", async () => {
    const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian", { in_squad: true }), ownedAscended("striker")] });
    client.putSquad.mockResolvedValue({ ascended_ids: ["guardian", "striker"], size: 5 });
    client.profile.mockResolvedValue({ ...PROFILE, squad: ["guardian", "striker"], ascendeds: [ownedAscended("guardian", { in_squad: true }), ownedAscended("striker", { in_squad: true })] });
    expect(wrapper.findAll(".ascended-card")).toHaveLength(1);
    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();
    await wrapper.find(".squad-control button").trigger("click");
    await flushPromises();
    expect(client.putSquad).toHaveBeenCalledWith(["guardian", "striker"]);
    expect(wrapper.find(".squad-control button").text()).toBe("Remove from squad");
    await wrapper.find(".squad-control button").trigger("click");
    await flushPromises();
    expect(client.putSquad).toHaveBeenLastCalledWith(["guardian"]);
  });

  it("explains full squads and active battles, and disables busy changes", async () => {
    const wrapper = mountPanel({ ...PROFILE, squad_size: 1, ascendeds: [ownedAscended("guardian", { in_squad: true }), ownedAscended("striker")] });
    await wrapper.find(".ascended-card").trigger("click");
    await flushPromises();
    expect(wrapper.find(".squad-control").text()).toContain("Squad full. Remove a member first.");
    expect(wrapper.find(".squad-control button").attributes("disabled")).toBeDefined();
    useAscensionStore().profile!.active_battle = "b1";
    await flushPromises();
    expect(wrapper.find(".squad-control").text()).toContain("Finish your battle first.");
    useAscensionStore().profile!.active_battle = null;
    useAscensionStore().profile!.squad_size = 5;
    useAscensionStore().busy = true;
    await flushPromises();
    expect(wrapper.find(".squad-control button").attributes("disabled")).toBeDefined();
  });
});


it("keeps the personality list visible while another preset is loading", async () => {
  const personalities = [{ id: "p1", type: "AGGRESSIVE", tier: 2 }];
  const wrapper = mount(PresetEditor, { props: { ascendedId: "guardian", ascendedName: "Guardian", personalities } });
  await flushPromises();
  client.preset.mockImplementationOnce(() => new Promise(() => {}));
  await wrapper.findAll('[role="tab"]').find(tab => tab.text() === "2")!.trigger("click");
  expect(wrapper.find(".personalities").text()).toContain("Aggressive");
  expect(wrapper.text()).not.toContain("Loading");
  expect(wrapper.find("input[role=switch]").attributes("disabled")).toBeDefined();
});

it("combines multiple tiers with type filters and preserves the acquired count", async () => {
  const wrapper = mountPanel({ ...PROFILE, ascendeds: [ownedAscended("guardian"), ownedAscended("striker", { tier_id: "rare", ascension_types: ["divine"] })] });
  expect(wrapper.find(".rail-count").text()).toBe("2/4 Acquired");
  expect(wrapper.findAll(".collected-zone .group").map(g => g.attributes("data-tier"))).toEqual(["common", "rare"]);
  await wrapper.find('[data-tier-filter="common"]').trigger("click");
  expect(wrapper.findAll(".ascended-card")).toHaveLength(1);
  await wrapper.find('[data-tier-filter="rare"]').trigger("click");
  expect(wrapper.findAll(".ascended-card")).toHaveLength(2);
  await wrapper.find('[data-type-filter="divine"]').trigger("click");
  expect(wrapper.findAll(".ascended-card .ascended-name").map(n => n.text())).toEqual(["Striker"]);
  expect(wrapper.find(".rail-count").text()).toBe("2/4 Acquired");
  await wrapper.find('[data-type-filter="enchant"]').trigger("click");
  expect(wrapper.findAll(".ascended-card")).toHaveLength(2);
});
