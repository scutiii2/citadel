import { flushPromises, mount, type DOMWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type EncounterPreview, type Profile } from "../api/AscensionClient";
import { CATALOG, ENCOUNTER, PROFILE, battleView, ownedAscended } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "../stores/ascension";
import EncounterPanel from "./EncounterPanel.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { rollEncounter: vi.fn(), declineEncounter: vi.fn(), startBattle: vi.fn(), profile: vi.fn() };
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
});

function mountPanel(profile: Profile = PROFILE, encounter: EncounterPreview | null = null) {
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = profile;
  store.encounter = encounter;
  return { store, wrapper: mount(EncounterPanel) };
}

/** The first of `buttons` whose text is `text` (or matches it). */
function button(buttons: DOMWrapper<HTMLButtonElement>[], text: string | RegExp): DOMWrapper<HTMLButtonElement> {
  const found = buttons.find((b) => (typeof text === "string" ? b.text() === text : text.test(b.text())));
  if (!found) throw new Error(`no button ${String(text)}`);
  return found;
}

describe("EncounterPanel", () => {
  it("shows the squad as preview cards with stats, using battle art", async () => {
    const { wrapper } = mountPanel(PROFILE, ENCOUNTER);
    await button(wrapper.findAll("button"), "Fight").trigger("click");
    expect(wrapper.find(".squad-choice img.portrait").attributes("src")).toBe("/ascended/guardian/sprite_battle.webp");
    expect(wrapper.find(".squad-choice .stats").exists()).toBe(true);
    expect(wrapper.find(".squad-choice .stars").exists()).toBe(true);
  });

  it("puts the selected fighter beside the opponent and summarizes squad availability", async () => {
    const { wrapper } = mountPanel(PROFILE, ENCOUNTER);
    await button(wrapper.findAll("button"), "Fight").trigger("click");
    expect(wrapper.find(".matchup .player .ascended-name").text()).toBe("Guardian");
    expect(wrapper.find(".matchup .wild .ascended-name").text()).toBe("Bruiser");
    expect(wrapper.find(".squad-summary").text()).toBe("1 ready · 0 fainted · 4 open slots");
    expect(wrapper.find("select[name='limit']").attributes("disabled")).toBeDefined();
    expect(wrapper.find(".battle-footer").text()).toContain("Guardian gets full XP if you win or capture");
  });

  it("locks battle plan changes while a start request is in flight", async () => {
    let resolve!: (value: ReturnType<typeof battleView>) => void;
    client.startBattle.mockReturnValue(new Promise(done => { resolve = done; }));
    const { wrapper } = mountPanel(PROFILE, ENCOUNTER);
    await button(wrapper.findAll("button"), "Fight").trigger("click");
    await wrapper.find("form.start-form").trigger("submit");
    expect(wrapper.find("select[name='preset']").attributes("disabled")).toBeDefined();
    expect(wrapper.findAll('[role="tab"]').every(t => t.attributes("disabled") !== undefined)).toBe(true);
    expect(button(wrapper.findAll("button"), "Back to encounter").attributes("disabled")).toBeDefined();
    resolve(battleView({ mode: "manual" }));
    await flushPromises();
  });
  it("lists the squad in order with empty slots and selects a ready fighter by keyboard", async () => {
    client.startBattle.mockResolvedValue(battleView({ mode: "manual" }));
    const profile = {
      ...PROFILE, squad: ["striker", "guardian"], squad_size: 5,
      ascendeds: [ownedAscended("guardian"), ownedAscended("striker")],
    };
    const { wrapper } = mountPanel(profile, ENCOUNTER);
    await button(wrapper.findAll("button"), "Fight").trigger("click");
    const squad = wrapper.find('[role="radiogroup"][aria-label="Your squad"]');
    const choices = squad.findAll('[role="radio"]');
    expect(choices.map(c => c.attributes("aria-label"))).toEqual(["Striker", "Guardian"]);
    expect(squad.findAll(".empty-slot")).toHaveLength(3);
    expect(wrapper.find(".matchup .player .ascended-name").text()).toBe("Striker");
    await choices[1]!.trigger("keydown.space");
    expect(wrapper.find(".matchup .player .ascended-name").text()).toBe("Guardian");
    await wrapper.find("form.start-form").trigger("submit");
    await flushPromises();
    expect(client.startBattle).toHaveBeenCalledWith(expect.objectContaining({ ascended_id: "guardian" }));
  });

  it("preselects the first ready squad member and blocks fainted members", async () => {
    const profile = {
      ...PROFILE, squad: ["guardian", "striker"], squad_size: 3,
      ascendeds: [ownedAscended("guardian", { faint_until: Date.now() / 1000 + 600 }), ownedAscended("striker")],
    };
    const { store, wrapper } = mountPanel(profile, ENCOUNTER);
    await button(wrapper.findAll("button"), "Fight").trigger("click");
    const choices = wrapper.findAll('[role="radio"]');
    expect(choices[0]!.attributes("aria-disabled")).toBe("true");
    expect(choices[1]!.attributes("aria-checked")).toBe("true");
    await choices[0]!.trigger("click");
    await choices[0]!.trigger("keydown.enter");
    expect(wrapper.find(".matchup .player .ascended-name").text()).toBe("Striker");
    store.profile = { ...profile, ascendeds: profile.ascendeds.map(a => ({ ...a, faint_until: Date.now() / 1000 + 600 })) };
    await wrapper.vm.$nextTick();
    expect(button(wrapper.findAll("button"), "Begin battle").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("No squad member is ready");
  });

  it("does not offer an owned ready Ascended outside the squad", () => {
    const profile = {
      ...PROFILE, squad: ["guardian"], squad_size: 5,
      ascendeds: [ownedAscended("guardian", { faint_until: Date.now() / 1000 + 600 }), ownedAscended("striker")],
    };
    const { wrapper } = mountPanel(profile, ENCOUNTER);
    expect(button(wrapper.findAll("button"), "Fight").attributes("disabled")).toBeDefined();
  });

  it("asks for another ready fighter if the selected member becomes fainted", async () => {
    const profile = { ...PROFILE, squad: ["guardian", "striker"], squad_size: 5,
      ascendeds: [ownedAscended("guardian"), ownedAscended("striker")] };
    const { store, wrapper } = mountPanel(profile, ENCOUNTER);
    await button(wrapper.findAll("button"), "Fight").trigger("click");
    store.profile = { ...profile, ascendeds: [ownedAscended("guardian", { faint_until: Date.now() / 1000 + 600 }), ownedAscended("striker")] };
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Select a ready squad member");
    expect(wrapper.text()).not.toContain("No squad member is ready");
    expect(button(wrapper.findAll("button"), "Begin battle").attributes("disabled")).toBeDefined();
  });
  it("looks for a wild Ascended once the cooldown is over", async () => {
    client.rollEncounter.mockResolvedValue(ENCOUNTER);
    const { store, wrapper } = mountPanel();

    const look = button(wrapper.findAll("button"), "Look for a wild Ascended");
    expect(look.attributes("disabled")).toBeUndefined();
    await look.trigger("click");
    await flushPromises();

    expect(client.rollEncounter).toHaveBeenCalledOnce();
    expect(store.encounter?.id).toBe("e1");
    expect(wrapper.find(".name").text()).toBe("Bruiser");
    expect(wrapper.emitted("stage")!.map((e) => e[0])).toEqual(["look", "preview"]);
  });

  it("waits out the cooldown with a countdown", () => {
    const { wrapper } = mountPanel({ ...PROFILE, next_roll_at: Date.now() / 1000 + 20 });

    const look = button(wrapper.findAll("button"), /Search ready in/);
    expect(look.text()).toMatch(/Search ready in 0:(19|20)/);
    expect(look.attributes("disabled")).toBeDefined();
  });

  it("declines for free", async () => {
    client.declineEncounter.mockResolvedValue({ ...ENCOUNTER, status: "declined" });
    const { store, wrapper } = mountPanel(PROFILE, ENCOUNTER);
    expect(wrapper.text()).toContain("Level 4");

    await button(wrapper.findAll("button"), "Decline · free").trigger("click");
    await flushPromises();

    expect(client.declineEncounter).toHaveBeenCalledExactlyOnceWith("e1");
    expect(store.encounter).toBeNull();
  });

  it("cannot fight with an empty squad and explains how to add a fighter", () => {
    const { wrapper } = mountPanel({ ...PROFILE, squad: [] }, ENCOUNTER);
    expect(button(wrapper.findAll("button"), "Fight").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Your squad is empty. Add an Ascended in Collection to battle.");
    expect(wrapper.find("form.start-form").exists()).toBe(false);
  });

  it("cannot fight while every Ascended is fainted", () => {
    const { wrapper } = mountPanel(
      { ...PROFILE, ascendeds: [ownedAscended("guardian", { faint_until: Date.now() / 1000 + 600, fainted: true })] },
      ENCOUNTER,
    );

    expect(button(wrapper.findAll("button"), "Fight").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("All your Ascended are fainted");
  });

  it("starts an autonomous battle only with a preset and an EMBLEM limit", async () => {
    client.startBattle.mockResolvedValue(battleView());
    const { wrapper } = mountPanel(PROFILE, ENCOUNTER);

    await button(wrapper.findAll("button"), "Fight").trigger("click");
    expect(wrapper.emitted("stage")!.map((e) => e[0])).toEqual(["preview", "setup"]);
    const form = wrapper.find("form.start-form");
    await form.findAll("[role=tab]").find((t) => t.text() === "Autonomous")!.trigger("click");
    const submit = form.find("button[type='submit']");
    expect(submit.attributes("disabled")).toBeDefined();
    expect(form.text()).toContain("Autonomous play needs a preset and an EMBLEM limit.");

    await form.find("select[name='preset']").setValue("2");
    await form.find("select[name='limit']").setValue("rare");
    expect(submit.attributes("disabled")).toBeUndefined();
    await form.trigger("submit");
    await flushPromises();

    expect(client.startBattle).toHaveBeenCalledExactlyOnceWith({
      encounter_id: "e1",
      ascended_id: "guardian",
      preset_slot: 2,
      mode: "autonomous",
      emblem_limit: "rare",
    });
  });

  it("starts a manual battle with no preset and no limit", async () => {
    client.startBattle.mockResolvedValue(battleView({ mode: "manual" }));
    const { wrapper } = mountPanel(PROFILE, ENCOUNTER);

    await button(wrapper.findAll("button"), "Fight").trigger("click");
    await wrapper.find("form.start-form").trigger("submit");
    await flushPromises();

    expect(client.startBattle).toHaveBeenCalledExactlyOnceWith({
      encounter_id: "e1",
      ascended_id: "guardian",
      preset_slot: null,
      mode: "manual",
      emblem_limit: null,
    });
  });
});
