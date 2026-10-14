import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type BattleView } from "../api/AscensionClient";
import { CATALOG, PROFILE, battleView, fighter } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "../stores/ascension";
import { usePlaybackStore } from "../stores/playback";
import ActionBar from "./ActionBar.vue";
import BattleArena from "./BattleArena.vue";
import BattleControls from "./BattleControls.vue";
import BattleResult from "./BattleResult.vue";
import EmblemPrompt from "./EmblemPrompt.vue";
import RoundLog from "./RoundLog.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { action: vi.fn(), emblem: vi.fn(), setMode: vi.fn(), forfeit: vi.fn(), profile: vi.fn() };
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

function withBattle(view: BattleView) {
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = PROFILE;
  store.battle = view;
  return store;
}

const manual = () =>
  battleView({
    mode: "manual",
    player: fighter("guardian", {
      abilities: [
        { id: "guardian_strike", name: "Strike", category: "ATTACK", percentage: 120, cooldown: 1, ready: true },
        { id: "guardian_rally", name: "Rally", category: "SUPPORT", percentage: 50, cooldown: 3, ready: false },
      ],
    }),
  });

describe("BattleArena", () => {
  it("shows each equipped passive effect directly below its fighter's stats", () => {
    const view = battleView({ player: { ...fighter('guardian'), passives: [
      { kind: 'defense_rating_bonus', params: { power_fraction: 0.4 } },
      { kind: 'low_hp_attack_bonus', params: { hp_below: 0.5, power_fraction: 0.2 } },
    ] } });
    withBattle(view);
    const wrapper = mount(BattleArena, { props: { battle: view } });
    const passives = wrapper.find('.player .passives');
    expect(wrapper.find('.player .stats').element.nextElementSibling).toBe(passives.element);
    expect(passives.findAll('li')).toHaveLength(2);
    expect(passives.text()).toContain('Defense rating rises by 40% of its Power.');
    expect(passives.text()).toContain('Below 50% HP');
    expect(wrapper.find('.wild .passives').exists()).toBe(false);
  });
  it("lists statuses beside buffs", () => {
    const view = battleView({
      player: fighter("guardian", { statuses: [{ id: "mark:prey", amount: 0, rounds_left: 2 }] }),
      wild: fighter("bruiser", { statuses: [{ id: "bleed", amount: 5, rounds_left: 3 }] }),
    });
    const wrapper = mount(BattleArena, { props: { battle: view } });
    expect(wrapper.text()).toContain("marked prey, 2 rounds left");
    expect(wrapper.text()).toContain("bleeding 5 a round, 3 rounds left");
  });
  it("shows both Ascended with their health written out, and what affects them", () => {
    const view = battleView({
      wild: fighter("bruiser", { hp: 20, buffs: [{ source: "bruiser_rally", stat: "power", amount: 4, rounds_left: 2 }] }),
    });
    withBattle(view);

    const wrapper = mount(BattleArena, { props: { battle: view } });

    expect(wrapper.findAll("[role='progressbar']").map((m) => m.attributes("aria-valuenow"))).toEqual(["80", "20"]);
    expect(wrapper.findAll("p.hp").map((p) => p.text())).toEqual(["HP 80 / 100", "HP 20 / 100"]);
    expect(wrapper.text()).toContain("+4 power, 2 rounds left");
    expect(wrapper.find(".round-number").text()).toBe("Round 1");
    expect(wrapper.find(".player .sprite img").attributes("src")).toBe("/ascended/guardian/sprite_battle.webp");
    expect(wrapper.find(".wild .sprite img").exists()).toBe(false);
    expect(wrapper.find(".wild .letter").text()).toBe("B");
  });
});

describe("BattleArena animation", () => {
  it("offers no skip control and clicking the arena leaves playback running", async () => {
    const store = withBattle(battleView());
    const playback = usePlaybackStore();
    playback.busy = true;
    playback.fx = { player: "lunge", wild: null };
    const wrapper = mount(BattleArena, { props: { battle: store.battle! } });
    expect(wrapper.find("button").exists()).toBe(false);
    await wrapper.find(".arena").trigger("click");
    expect(playback.busy).toBe(true);
    expect(playback.fx.player).toBe("lunge");
  });

  it("shows only the EMBLEM through capture struggle and restores the fighter on release", async () => {
    const store = withBattle(battleView());
    const playback = usePlaybackStore();
    const wrapper = mount(BattleArena, { props: { battle: store.battle! } });
    playback.ball = { player: null, wild: { phase: "absorb", emblem: "rare" } };
    playback.fx = { player: null, wild: "absorb" };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".wild .sprite").classes()).not.toContain("concealed");
    expect(wrapper.find(".wild .capture-flow").exists()).toBe(true);
    for (const phase of ["wobble", "still", "caught"] as const) {
      playback.ball = { player: null, wild: { phase, emblem: "common", strain: 2 } };
      await wrapper.vm.$nextTick();
      expect(wrapper.find(".wild .sprite").classes()).toContain("concealed");
      expect(wrapper.find(`.wild .ball-${phase}`).exists()).toBe(true);
    }
    playback.ball = { player: null, wild: { phase: "open", emblem: "common" } };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".wild .sprite").classes()).not.toContain("concealed");
    expect(wrapper.findAll(".wild .stone-fragment")).toHaveLength(2);
  });

  const sheet = {
    url: "/ascended/guardian/spreadsheet_animation.webp", columns: 4, rows: 6,
    states: { idle: { row: 0, frames: 4, frame_ms: 180, loop: true }, attack: { row: 1, frames: 4, frame_ms: 100, loop: false } },
  };

  it("keeps the static battle sprite even when animation metadata exists", async () => {
    const store = withBattle(battleView());
    store.catalog = { ...CATALOG, ascendeds: CATALOG.ascendeds.map((a) => (a.id === "guardian" ? { ...a, art: { ...a.art, animation: sheet } } : a)) };
    const playback = usePlaybackStore();
    const wrapper = mount(BattleArena, { props: { battle: store.battle! } });
    expect(wrapper.find(".player .sprite img").attributes("src")).toBe("/ascended/guardian/sprite_battle.webp");
    expect(wrapper.find(".animated-sprite").exists()).toBe(false);
    playback.fx = { player: "lunge", wild: null };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".player .sprite").classes()).toContain("fx-lunge");
    await wrapper.find(".player .sprite img").trigger("error");
    expect(wrapper.find(".player .sprite img").exists()).toBe(false);
    expect(wrapper.find(".player .letter").text()).toBe("G");
  });

});

describe("RoundLog", () => {
  it("lists the rounds in words, latest first", () => {
    const view = battleView({
      history: [
        {
          round: 1,
          actions: { player: ["ability:guardian_strike", "ATTACK"], wild: ["attack", "ATTACK"] },
          events: [{ type: "attack", side: "player", damage: 18, protected: false, target_hp: 20 }],
        },
        {
          round: 2,
          actions: { player: ["attack", "ATTACK"], wild: ["attack", "ATTACK"] },
          events: [{ type: "attack", side: "wild", damage: 5, protected: false, target_hp: 75 }],
        },
      ],
    });
    withBattle(view);

    const wrapper = mount(RoundLog, { props: { battle: view } });

    expect(wrapper.findAll(".title").map((t) => t.text())).toEqual(["Round 2", "Round 1"]);
    expect(wrapper.findAll(".now").map((n) => n.text())).toEqual(["Latest"]);
    const first = wrapper.findAll(".round")[1]!;
    expect(first.findAll(".who").map((w) => w.text())).toEqual(["Guardian", "Bruiser"]);
    expect(first.findAll(".move").map((m) => m.text())).toEqual(["Strike", "Attack"]);
    expect(first.findAll(".move").map((m) => m.classes().find((c) => c.startsWith("tone-")))).toEqual(["tone-attack", "tone-attack"]);
    expect(wrapper.text()).toContain("Guardian hits for 18; Bruiser has 20 HP left");
    expect(wrapper.find(".rounds").attributes("aria-live")).toBe("polite");
  });

  it("says when no round was played yet", () => {
    const view = battleView({ history: [] });
    withBattle(view);

    expect(mount(RoundLog, { props: { battle: view } }).text()).toContain("No rounds yet.");
  });
});

describe("ActionBar", () => {
  it("shows all catalog moves and disables moves not equipped or below their required level", async () => {
    const view = manual();
    view.player.level = 10;
    view.player.abilities = view.player.abilities.filter(a => a.id === 'guardian_strike');
    const store = withBattle(view);
    store.catalog = { ...CATALOG, ascendeds: CATALOG.ascendeds.map(a => a.id === 'guardian' ? {
      ...a, abilities: [...a.abilities, { ...a.abilities[0]!, id: 'guardian_nova', name: 'Nova', unlock_level: 20 }],
    } : a) };
    const wrapper = mount(ActionBar, { props: { battle: view } });
    const buttons = wrapper.findAll('button.action');
    expect(buttons.map(b => b.find('.action-name').text())).toEqual(['Attack', 'Strike', 'Rally', 'Nova', 'Flee', 'Catch']);
    expect(buttons[2]!.attributes('disabled')).toBeDefined();
    expect(buttons[2]!.text()).toContain('Not equipped for this battle');
    expect(buttons[3]!.attributes('disabled')).toBeDefined();
    expect(buttons[3]!.text()).toContain('Requires level 20');
    await buttons[3]!.trigger('click');
    expect(client.action).not.toHaveBeenCalled();
  });
  it("offers one button per legal action and shows abilities cooling down", () => {
    const view = manual();
    withBattle(view);

    const wrapper = mount(ActionBar, { props: { battle: view } });

    const buttons = wrapper.findAll("button.action");
    expect(buttons.map((b) => b.find(".action-name").text())).toEqual(["Attack", "Strike", "Rally", "Flee", "Catch"]);
    expect(buttons[1]!.attributes("disabled")).toBeUndefined();
    expect(buttons[2]!.attributes("disabled")).toBeDefined();
    expect(buttons[2]!.text()).toContain("Cooling down (3 rounds)");
  });

  it("describes an ability's effects on its button", () => {
    const view = manual();
    view.actions = view.actions.map((a) => (a.ability_id ? { ...a, effects: [{ kind: "bleed", percentage: 20, rounds: 3 }] } : a));
    withBattle(view);

    const wrapper = mount(ActionBar, { props: { battle: view } });

    expect(wrapper.findAll("button.action")[1]!.find(".action-detail").text()).toContain("Bleeds 20% for 3 rounds");
  });

  it("sends the chosen action with the round and revision it saw", async () => {
    const view = manual();
    withBattle(view);
    client.action.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 2 }));
    const wrapper = mount(ActionBar, { props: { battle: view } });

    await wrapper.findAll("button.action")[1]!.trigger("click");
    await flushPromises();

    expect(client.action).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 1 }, { kind: "ability", ability_id: "guardian_strike" });
  });

  it("asks which EMBLEM to throw for a catch", async () => {
    const view = manual();
    withBattle(view);
    client.action.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 2 }));
    const wrapper = mount(ActionBar, { props: { battle: view } });

    await wrapper.findAll("button.action")[4]!.trigger("click");
    expect(client.action).not.toHaveBeenCalled();
    await wrapper.findAll("button").find((b) => b.text() === "Common (2)")!.trigger("click");
    await flushPromises();

    expect(client.action).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 1 }, { kind: "catch", emblem_tier: "common" });
  });
});

describe("BattleControls", () => {
  it("shows icon-only controls with accessible names and tooltips", () => {
    const view = manual();
    withBattle(view);
    const wrapper = mount(BattleControls, { props: { battle: view } });
    const tabs = wrapper.findAll("[role=tab]");
    expect(tabs.map((tab) => tab.attributes("aria-label"))).toEqual(["Manual", "Autonomous"]);
    expect(tabs.map((tab) => tab.attributes("title"))).toEqual(["Manual", "Autonomous"]);
    expect(tabs.map((tab) => tab.text())).toEqual(["", ""]);
    const forfeit = wrapper.find("button.forfeit");
    expect(forfeit.attributes("aria-label")).toBe("Forfeit");
    expect(forfeit.attributes("title")).toBe("Forfeit");
    expect(forfeit.text()).toBe("");
  });

  it("keeps a battle without an EMBLEM limit manual", async () => {
    const view = battleView({ mode: "manual", emblem_limit: null });
    withBattle(view);
    const wrapper = mount(BattleControls, { props: { battle: view } });

    const autonomous = wrapper.findAll("[role=tab]").find((b) => b.attributes("aria-label") === "Autonomous")!;
    expect(autonomous.attributes("disabled")).toBeDefined();
    await autonomous.trigger("click");

    expect(client.setMode).not.toHaveBeenCalled();
  });

  it("switches to autonomous between rounds", async () => {
    const view = battleView({ mode: "manual" });
    withBattle(view);
    client.setMode.mockResolvedValue(battleView());
    const wrapper = mount(BattleControls, { props: { battle: view } });

    await wrapper.findAll("[role=tab]").find((b) => b.attributes("aria-label") === "Autonomous")!.trigger("click");
    await flushPromises();

    expect(client.setMode).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 1 }, "autonomous", null);
  });

  it("forfeits only after confirming", async () => {
    const view = manual();
    withBattle(view);
    client.forfeit.mockResolvedValue(
      battleView({ status: "terminal", phase: "terminal", result: { kind: "forfeited", faint_until: 1_700_000_600 } }),
    );
    const wrapper = mount(BattleControls, { props: { battle: view } });

    await wrapper.find("button.danger").trigger("click");
    expect(client.forfeit).not.toHaveBeenCalled();
    await wrapper.find("button.confirm").trigger("click");
    await flushPromises();

    expect(client.forfeit).toHaveBeenCalledExactlyOnceWith("b1");
  });
});

describe("EmblemPrompt", () => {
  const prompting = () =>
    battleView({
      phase: "awaiting_emblem",
      revision: 4,
      prompt: { deadline: 0, seconds_left: 5, permitted_tiers: ["common"], owned: { common: 2 } },
    });

  it("offers the permitted tiers with their counts while time is left", async () => {
    const store = withBattle(prompting());
    store.promptRemaining = 3.2;
    store.promptTotal = 5;
    client.emblem.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 5 }));
    const wrapper = mount(EmblemPrompt);

    expect(wrapper.find(".em-ring").text()).toBe("4s");
    expect(wrapper.text()).toContain("4 s left");
    await wrapper.findAll("button.tier").find((b) => b.text().startsWith("Common"))!.trigger("click");
    await flushPromises();

    expect(client.emblem).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 4 }, "common");
  });

  it("disables the tiers at zero", () => {
    const store = withBattle(prompting());
    store.promptRemaining = 0;
    store.promptTotal = 5;

    const wrapper = mount(EmblemPrompt);

    expect(wrapper.text()).toContain("Time is up");
    expect(wrapper.findAll("button.tier").find((b) => b.text().startsWith("Common"))!.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Your Ascended will decide this turn.");
  });
});

describe("BattleResult", () => {
  it("shows bench XP beneath the fighter reward, including level-ups", () => {
    const view = battleView({ status: "terminal", phase: "terminal", result: {
      kind: "won", xp: 40, level_before: 1, level_after: 1,
      squad_xp: [
        { ascended_id: "striker", name: "Striker", xp: 10, level_before: 1, level_after: 2 },
        { ascended_id: "scout", name: "Scout", xp: 10, level_before: 3, level_after: 3 },
      ],
    } });
    withBattle(view);
    const wrapper = mount(BattleResult, { props: { battle: view } });
    expect(wrapper.find(".squad-xp").text()).toContain("Squad XP");
    expect(wrapper.findAll(".squad-xp li").map(r => r.text())).toEqual(["+40 XP · Guardian", "+10 XP · Striker, now level 2", "+10 XP · Scout"]);
    expect(wrapper.find(".reward strong").text()).toBe("+40 XP");
  });
  it("shows a capture with the personalities it revealed, and Back leaves it", async () => {
    vi.useFakeTimers();
    const view = battleView({
      status: "terminal",
      phase: "terminal",
      result: {
        kind: "captured",
        xp: 30,
        insignia: 12,
        essence: 2,
        essence_tier_id: "rare",
        level_before: 3,
        level_after: 4,
        ascended_id: "bruiser",
        copies_granted: 2,
        copies: 2,
        tier_id: "rare",
        awarded_personality: { id: "new-record", type: "BOLD", tier: 2 },
        awarded_index: 1,
        revealed_personalities: [
          { id: "w1", type: "CAUTIOUS", tier: 1 },
          { id: "w2", type: "BOLD", tier: 2 },
        ],
      },
    });
    const store = withBattle(view);
    const wrapper = mount(BattleResult, { props: { battle: view } });

    const text = wrapper.text();
    expect(text).toContain("Captured");
    expect(wrapper.findAll(".reward")[0]!.text()).toBe("+30 XPfor Guardian, now level 4");
    expect(text).toContain("+12 Insignia");
    expect(wrapper.findAll(".reward")[2]!.text()).toBe("+2 Rare essencefor upgrading stars");
    expect(wrapper.findAll(".reward")[2]!.find("img.em-essence").attributes("src")).toContain("essence_rare.webp");
    expect(wrapper.findAll(".reward")[3]!.text()).toBe("+2 copiesof Bruiser, at Rare");
    expect(text).toContain("Cautious · tier 1");
    expect(text).not.toContain("(now yours)");
    await nextTick();
    expect(wrapper.find(".revealed li.lit").exists()).toBe(true);

    vi.advanceTimersByTime(6000);
    await nextTick();
    expect(wrapper.find(".revealed li.won").text()).toBe("Bold · tier 2 (now yours)");
    expect(wrapper.findAll(".revealed li.dim")).toHaveLength(1);
    vi.useRealTimers();

    await wrapper.findAll("button").find((b) => b.text() === "Back to encounters")!.trigger("click");
    await flushPromises();

    expect(store.battle).toBeNull();
    expect(client.profile).toHaveBeenCalledOnce();
  });

  it("says when the Ascended fainted", () => {
    const view = battleView({ status: "terminal", phase: "terminal", result: { kind: "knocked_out", faint_until: 1_700_000_600 } });
    withBattle(view);

    const text = mount(BattleResult, { props: { battle: view } }).text();

    expect(text).toContain("Your Ascended was knocked out");
    expect(text).toContain("Guardian fainted and needs rest before its next battle.");
  });
});
