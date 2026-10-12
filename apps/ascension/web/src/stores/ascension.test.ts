import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type BattleView, type EmblemPromptState } from "../api/AscensionClient";
import { CATALOG, ENCOUNTER, PROFILE, battleView, shopWindow } from "../api/AscensionClient.fixtures";
import { ApiError } from "../api/http";
import { useSessionStore } from "./session";
import { RECONNECT_MS, ROUND_PACE_MS, useAscensionStore } from "./ascension";

vi.mock("../api/AscensionClient", () => {
  const client = {
    catalog: vi.fn(),
    profile: vi.fn(),
    putSquad: vi.fn(),
    createProfile: vi.fn(),
    personalities: vi.fn(),
    preset: vi.fn(),
    savePreset: vi.fn(),
    rollEncounter: vi.fn(),
    encounter: vi.fn(),
    declineEncounter: vi.fn(),
    startBattle: vi.fn(),
    battle: vi.fn(),
    action: vi.fn(),
    emblem: vi.fn(),
    advance: vi.fn(),
    setMode: vi.fn(),
    forfeit: vi.fn(),
    buyEmblems: vi.fn(),
    shop: vi.fn(),
    buyOffer: vi.fn(),
    sellCopy: vi.fn(),
    resetProfile: vi.fn(),
  };
  return { useAscensionClient: () => client };
});

const client = vi.mocked(useAscensionClient());
// The server's deadline is deliberately nonsense: only seconds_left may count.
const PROMPT: EmblemPromptState = { deadline: 0, seconds_left: 5, permitted_tiers: ["common"], owned: { common: 2 } };

let visibility: DocumentVisibilityState = "visible";
let store: ReturnType<typeof useAscensionStore> | null = null;

beforeAll(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
});

function setVisibility(state: DocumentVisibilityState): void {
  visibility = state;
  document.dispatchEvent(new Event("visibilitychange"));
}

async function attached(): Promise<ReturnType<typeof useAscensionStore>> {
  setActivePinia(createPinia());
  useSessionStore().status = "ready";
  store = useAscensionStore();
  store.attach();
  await flushPromises();
  return store;
}

async function attachedWith(view: BattleView): Promise<ReturnType<typeof useAscensionStore>> {
  client.profile.mockResolvedValue({ ...PROFILE, active_battle: view.id });
  client.battle.mockResolvedValue(view);
  return attached();
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "performance"] });
  visibility = "visible";
  client.catalog.mockResolvedValue(CATALOG);
  client.profile.mockResolvedValue(PROFILE);
});

afterEach(() => {
  store?.detach();
  store = null;
  vi.useRealTimers();
});

describe("loading", () => {
  it("asks for a starter while there is no profile", async () => {
    client.profile.mockRejectedValue(new ApiError(404, "no profile yet; choose a starter first"));
    const s = await attached();

    expect(s.needsStarter).toBe(true);
    expect(s.profile).toBeNull();

    client.createProfile.mockResolvedValue(PROFILE);
    await s.createProfile("guardian");

    expect(client.createProfile).toHaveBeenCalledExactlyOnceWith("guardian");
    expect(s.profile).toEqual(PROFILE);
    expect(s.needsStarter).toBe(false);
  });

  it("restores a pending encounter instead of rolling a new one", async () => {
    client.profile.mockResolvedValue({ ...PROFILE, pending_encounter: "e1" });
    client.encounter.mockResolvedValue(ENCOUNTER);
    const s = await attached();

    expect(client.encounter).toHaveBeenCalledExactlyOnceWith("e1");
    expect(s.encounter?.id).toBe("e1");
    expect(client.rollEncounter).not.toHaveBeenCalled();
  });

  it("shows the page as unavailable on 502 and loads again on retry", async () => {
    client.catalog.mockRejectedValueOnce(new ApiError(502, "Ascension is not available right now"));
    const s = await attached();

    expect(s.unavailable).toBe(true);

    await s.retry();

    expect(s.unavailable).toBe(false);
    expect(s.loaded).toBe(true);
  });

  it("forgets everything when the session ends", async () => {
    const s = await attachedWith(battleView());

    useSessionStore().end();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 3);

    expect(s.battle).toBeNull();
    expect(s.profile).toBeNull();
    expect(s.loaded).toBe(false);
    expect(client.advance).not.toHaveBeenCalled();
  });
});

describe("the autonomous loop", () => {
  it("plays a round every 1.5 s until the battle ends", async () => {
    const s = await attachedWith(battleView());
    client.advance
      .mockResolvedValueOnce(battleView({ round: 2, revision: 2 }))
      .mockResolvedValueOnce(
        battleView({ round: 3, revision: 3, status: "terminal", phase: "terminal", result: { kind: "won", xp: 5, insignia: 3 } }),
      );

    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS - 1);
    expect(client.advance).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(client.advance).toHaveBeenLastCalledWith("b1", { round: 1, revision: 1 });
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS);
    expect(client.advance).toHaveBeenLastCalledWith("b1", { round: 2, revision: 2 });
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 5);

    expect(client.advance).toHaveBeenCalledTimes(2);
    expect(s.battle?.result?.kind).toBe("won");
    // Loaded once, then again for the rewards.
    expect(client.profile).toHaveBeenCalledTimes(2);
  });

  it("stops when the page is left", async () => {
    const s = await attachedWith(battleView());

    s.detach();
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 5);

    expect(client.advance).not.toHaveBeenCalled();
  });

  it("pauses while the page is hidden and resumes from a fresh view", async () => {
    await attachedWith(battleView());

    setVisibility("hidden");
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 5);
    expect(client.advance).not.toHaveBeenCalled();

    client.battle.mockClear();
    setVisibility("visible");
    await flushPromises();
    expect(client.battle).toHaveBeenCalledExactlyOnceWith("b1");

    client.advance.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 2 }));
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS);
    expect(client.advance).toHaveBeenCalledTimes(1);
  });

  it("pauses on a network error and asks again every 3 s until it answers", async () => {
    const s = await attachedWith(battleView());
    client.advance.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS);
    expect(s.reconnecting).toBe(true);

    client.battle.mockClear();
    client.battle.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValueOnce(battleView({ round: 2, revision: 2 }));
    await vi.advanceTimersByTimeAsync(RECONNECT_MS);
    expect(client.battle).toHaveBeenCalledTimes(1);
    expect(s.reconnecting).toBe(true);
    await vi.advanceTimersByTimeAsync(RECONNECT_MS);
    expect(client.battle).toHaveBeenCalledTimes(2);
    expect(s.reconnecting).toBe(false);

    client.advance.mockResolvedValue(battleView({ mode: "manual", round: 3, revision: 3 }));
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS);
    expect(client.advance).toHaveBeenLastCalledWith("b1", { round: 2, revision: 2 });
  });

  it("stops and shows the page as unavailable on 502", async () => {
    const s = await attachedWith(battleView());
    client.advance.mockRejectedValue(new ApiError(502, "Ascension is not available right now"));

    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 5);

    expect(s.unavailable).toBe(true);
    expect(client.advance).toHaveBeenCalledTimes(1);
  });
});

describe("manual play", () => {
  it("never advances on its own and does not retry a stale action", async () => {
    const s = await attachedWith(battleView({ mode: "manual" }));
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 5);
    expect(client.advance).not.toHaveBeenCalled();

    client.action.mockRejectedValue(new ApiError(409, "the battle moved on; reload it and try again"));
    client.battle.mockClear();
    client.battle.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 3 }));
    await s.act({ kind: "attack" });

    expect(client.action).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 1 }, { kind: "attack" });
    expect(client.battle).toHaveBeenCalledExactlyOnceWith("b1");
    expect(s.battle?.revision).toBe(3);
    expect(s.error).toBe("the battle moved on; reload it and try again");
  });
});

describe("the EMBLEM prompt", () => {
  it("counts down on the local clock and lets the server settle it at zero", async () => {
    const s = await attachedWith(battleView({ phase: "awaiting_emblem", revision: 4, prompt: PROMPT }));

    expect(s.promptOpen).toBe(true);
    expect(s.promptRemaining).toBe(5);
    expect(s.promptTotal).toBe(5);

    await vi.advanceTimersByTimeAsync(2000);
    expect(s.promptRemaining).toBeCloseTo(3, 1);

    client.advance.mockResolvedValue(battleView({ round: 2, revision: 5 }));
    await vi.advanceTimersByTimeAsync(3000);

    expect(client.advance).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 4 });
    expect(s.promptOpen).toBe(false);
  });

  it("throws the chosen EMBLEM before the time is up", async () => {
    const s = await attachedWith(battleView({ phase: "awaiting_emblem", revision: 4, prompt: PROMPT }));
    client.emblem.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 5 }));

    await s.answerEmblem("common");
    await vi.advanceTimersByTimeAsync(6000);

    expect(client.emblem).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 4 }, "common");
    expect(client.advance).not.toHaveBeenCalled();
  });

  it("treats a late answer like an expired prompt: refresh and continue", async () => {
    const s = await attachedWith(battleView({ phase: "awaiting_emblem", revision: 4, prompt: PROMPT }));
    client.emblem.mockRejectedValue(new ApiError(409, "the prompt has expired; advance the battle instead"));
    client.battle.mockResolvedValue(
      battleView({ phase: "awaiting_emblem", revision: 4, prompt: { ...PROMPT, seconds_left: 0 } }),
    );
    client.advance.mockResolvedValue(battleView({ mode: "manual", round: 2, revision: 5 }));

    await s.answerEmblem("common");
    await vi.advanceTimersByTimeAsync(0);

    expect(client.advance).toHaveBeenCalledExactlyOnceWith("b1", { round: 1, revision: 4 });
    expect(s.battle?.revision).toBe(5);
  });
});

describe("resetting progress", () => {
  it("clears profile, encounter and battle, asks for a starter and stops the loop", async () => {
    const s = await attachedWith(battleView({ mode: "autonomous" }));
    s.encounter = ENCOUNTER;
    client.resetProfile.mockResolvedValue({ reset: true });

    await expect(s.resetProgress()).resolves.toBe(true);

    expect(client.resetProfile).toHaveBeenCalledTimes(1);
    expect(s.profile).toBeNull();
    expect(s.encounter).toBeNull();
    expect(s.battle).toBeNull();
    expect(s.needsStarter).toBe(true);
    expect(s.busy).toBe(false);
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS * 5);
    expect(client.advance).not.toHaveBeenCalled();
  });

  it("keeps everything and says why when the server refuses", async () => {
    const s = await attached();
    client.resetProfile.mockRejectedValue(new ApiError(409, "finish or forfeit your battle before resetting"));

    await expect(s.resetProgress()).resolves.toBe(false);

    expect(s.error).toBe("finish or forfeit your battle before resetting");
    expect(s.profile).toEqual(PROFILE);
    expect(s.needsStarter).toBe(false);
    expect(s.busy).toBe(false);
  });

  it("keeps the autonomous loop running after a refused reset", async () => {
    const s = await attachedWith(battleView({ mode: "autonomous" }));
    client.resetProfile.mockRejectedValue(new ApiError(409, "finish or forfeit your battle before resetting"));
    client.advance.mockResolvedValue(battleView({ round: 2, revision: 2 }));

    await s.resetProgress();
    await vi.advanceTimersByTimeAsync(ROUND_PACE_MS);

    expect(client.advance).toHaveBeenCalledTimes(1);
    expect(s.battle).not.toBeNull();
  });

  it("marks the page unavailable on a 502 and keeps the state", async () => {
    const s = await attached();
    client.resetProfile.mockRejectedValue(new ApiError(502, "down"));

    await expect(s.resetProgress()).resolves.toBe(false);

    expect(s.unavailable).toBe(true);
    expect(s.profile).toEqual(PROFILE);
  });

  it("ignores a reset while another change is running", async () => {
    const s = await attached();
    let finish: (value: { reset: boolean }) => void = () => undefined;
    client.resetProfile.mockReturnValue(new Promise((resolve) => (finish = resolve)));

    const first = s.resetProgress();
    await expect(s.resetProgress()).resolves.toBe(false);
    expect(client.resetProfile).toHaveBeenCalledTimes(1);

    finish({ reset: true });
    await expect(first).resolves.toBe(true);
  });
});

describe("rotating shop", () => {
  it("loads the window and counts down from the answer on this device's clock", async () => {
    const s = await attached();
    client.shop.mockResolvedValue(shopWindow({ seconds_left: 120 }));
    const before = Date.now() / 1000;

    await s.loadShop();

    expect(s.shop?.offers).toHaveLength(2);
    expect(s.shopEndsAt).toBeGreaterThanOrEqual(before + 120);
    expect(s.shopEndsAt).toBeLessThan(before + 125);
  });

  it("buys an offer, then reloads the window and the profile", async () => {
    const s = await attached();
    client.shop.mockResolvedValue(shopWindow());
    client.buyOffer.mockResolvedValue({ kind: "copies", ascended_id: "guardian", tier_id: "common", copies_granted: 1, price: 40, slot: 0, rotation: 46, left: 2 });
    await s.loadShop();

    const bought = await s.buyOffer(s.shop!.offers[0]!);

    expect(client.buyOffer).toHaveBeenCalledWith(46, 0);
    expect(bought?.left).toBe(2);
    expect(client.shop).toHaveBeenCalledTimes(2);
  });

  it("reloads the window when the shop says it has refreshed", async () => {
    const s = await attached();
    client.shop.mockResolvedValue(shopWindow());
    client.buyOffer.mockRejectedValue(new ApiError(409, "the shop has refreshed; look at the new offers"));
    await s.loadShop();

    await s.buyOffer(s.shop!.offers[0]!);

    expect(s.error).toBe("the shop has refreshed; look at the new offers");
    expect(client.shop).toHaveBeenCalledTimes(2);
  });
});


describe("squad", () => {
  it("keeps profile squad order, appends and removes with a profile refresh", async () => {
    const s = await attached();
    s.profile = { ...PROFILE, squad: ["striker", "guardian"], ascendeds: [PROFILE.ascendeds[0]!, { ...PROFILE.ascendeds[0]!, ascended_id: "striker" }] };
    expect(s.squadMembers.map(a => a.ascended_id)).toEqual(["striker", "guardian"]);
    client.putSquad.mockResolvedValue({ ascended_ids: ["striker", "guardian", "bruiser"], size: 5 });
    client.profile.mockResolvedValue({ ...s.profile, squad: ["striker", "guardian", "bruiser"] });
    await s.addToSquad("bruiser");
    expect(client.putSquad).toHaveBeenLastCalledWith(["striker", "guardian", "bruiser"]);
    expect(s.squadIds).toEqual(["striker", "guardian", "bruiser"]);
    client.profile.mockResolvedValue({ ...s.profile, squad: ["guardian", "bruiser"] });
    await s.removeFromSquad("striker");
    expect(client.putSquad).toHaveBeenLastCalledWith(["guardian", "bruiser"]);
    expect(s.squadIds).toEqual(["guardian", "bruiser"]);
  });

  it("reports a refused change, clears busy, and preserves the squad", async () => {
    const s = await attached();
    client.putSquad.mockRejectedValue(new ApiError(409, "Finish your battle first."));
    expect(await s.setSquad(["striker"])).toBeNull();
    expect(s.error).toContain("Finish your battle first.");
    expect(s.busy).toBe(false);
    expect(s.squadIds).toEqual(["guardian"]);
  });

  it("stays busy through profile refresh and ignores another squad change", async () => {
    const s = await attached();
    let resolve!: (value: { ascended_ids: string[]; size: number }) => void;
    client.putSquad.mockReturnValue(new Promise(done => { resolve = done; }));
    const change = s.setSquad(["guardian"]);
    expect(s.busy).toBe(true);
    expect(await s.setSquad(["striker"])).toBeNull();
    expect(client.putSquad).toHaveBeenCalledTimes(1);
    resolve({ ascended_ids: ["guardian"], size: 5 });
    await change;
    expect(s.busy).toBe(false);
  });
});
