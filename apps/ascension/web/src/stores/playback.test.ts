import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BattleView, HistoryRound } from "../api/AscensionClient";
import { battleView, fighter } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "./ascension";
import { usePlaybackStore } from "./playback";

vi.mock("../api/AscensionClient", () => ({ useAscensionClient: () => ({}) }));

const settle = () => vi.advanceTimersByTimeAsync(0);

const ATTACK: HistoryRound = {
  round: 1,
  actions: { player: ["attack", "ATTACK"], wild: ["attack", "ATTACK"] },
  events: [{ type: "attack", side: "player", damage: 27, protected: false, target_hp: 53 }],
};

async function setup() {
  setActivePinia(createPinia());
  const ascension = useAscensionStore();
  const playback = usePlaybackStore();
  const before: BattleView = battleView({ history: [] });
  ascension.battle = before;
  await settle();
  return { ascension, playback, before };
}

const after = (before: BattleView, extra: Partial<BattleView> = {}): BattleView =>
  battleView({ history: [ATTACK], wild: fighter("bruiser", { hp: 53 }), ...extra, id: before.id });
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("battle playback", () => {
  it("plays a new round step by step and shows the old health until the hit lands", async () => {
    const { ascension, playback, before } = await setup();

    ascension.battle = after(before);
    await settle();
    expect(playback.busy).toBe(true);
    expect(playback.fx.player).toBe("lunge");
    expect(playback.hp).toEqual({ player: 80, wild: 80 });

    await vi.advanceTimersByTimeAsync(320);
    expect(playback.fx.wild).toBe("hit");
    expect(playback.hp).toEqual({ player: 80, wild: 53 });
    expect(playback.floating?.text).toBe("-27");

    await vi.advanceTimersByTimeAsync(460);
    expect(playback.busy).toBe(false);
    expect(playback.hp).toBeNull();
    expect(playback.fx).toEqual({ player: null, wild: null });
  });

  it("does not play a battle that is opened or restored", async () => {
    const { ascension, playback } = await setup();

    ascension.battle = battleView({ id: "other", history: [ATTACK] });
    await settle();

    expect(playback.busy).toBe(false);
  });

  it("jumps to the end when skipped", async () => {
    const { ascension, playback, before } = await setup();
    ascension.battle = after(before);
    await settle();

    playback.skip();
    await settle();

    expect(playback.busy).toBe(false);
    expect(playback.hp).toBeNull();
  });

  it("does not play while an EMBLEM prompt is open", async () => {
    const { ascension, playback, before } = await setup();

    ascension.battle = after(before, { phase: "awaiting_emblem" });
    await settle();

    expect(playback.busy).toBe(false);
  });

  it("plays even when the system asks for reduced motion", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { ascension, playback, before } = await setup();

    ascension.battle = after(before);
    await settle();

    expect(playback.busy).toBe(true);
  });

  it("queues a round that arrives while another plays", async () => {
    const { ascension, playback, before } = await setup();
    ascension.battle = after(before);
    await settle();

    ascension.battle = battleView({ id: before.id, history: [ATTACK, { ...ATTACK, round: 2 }] });
    await settle();
    await vi.advanceTimersByTimeAsync(780);
    expect(playback.busy).toBe(true);

    await vi.advanceTimersByTimeAsync(780);
    expect(playback.busy).toBe(false);
  });
});
