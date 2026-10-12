import { describe, expect, it } from "vitest";
import { stepsFor } from "./battleCues";

describe("stepsFor", () => {
  it("plays an attack as a lunge, then a hit that lowers the target's health", () => {
    const steps = stepsFor([{ type: "attack", side: "player", damage: 27, protected: false, target_hp: 73 }]);

    expect(steps.map((s) => s.fx)).toEqual([{ player: "lunge" }, { wild: "hit" }]);
    expect(steps[1]!.float).toEqual({ side: "wild", text: "-27", tone: "damage" });
    expect(steps[1]!.hp).toEqual({ side: "wild", value: 73 });
  });

  it("shows a defended hit differently", () => {
    const [, hit] = stepsFor([{ type: "attack", side: "wild", damage: 9, protected: true, target_hp: 50 }]);

    expect(hit!.fx).toEqual({ player: "guarded" });
    expect(hit!.float!.tone).toBe("guarded");
  });

  it("covers defense, support and flee", () => {
    expect(stepsFor([{ type: "defense", side: "player", rating: 4 }])[0]!.fx).toEqual({ player: "guard" });
    const support = stepsFor([{ type: "support", side: "wild", stat: "speed", amount: 3 }])[0]!;
    expect(support.fx).toEqual({ wild: "boost" });
    expect(support.float!.text).toBe("+3 Speed");
    expect(stepsFor([{ type: "flee", side: "player", chance: 0.5, success: true }])[0]!.fx).toEqual({ player: "flee-away" });
    expect(stepsFor([{ type: "flee", side: "player", chance: 0.5, success: false }])[0]!.fx).toEqual({ player: "flee-fail" });
  });

  it("throws an EMBLEM at the other side, wobbles, then closes or breaks free", () => {
    const caught = stepsFor([{ type: "capture_attempt", side: "player", emblem: "rare", chance: 0.4, success: true }]);
    expect(caught.map((s) => s.ball?.wild?.phase)).toEqual(["throw", "throw", "wobble", "wobble", "wobble", "still", "caught"]);
    expect(caught[0]!.ball!.wild!.emblem).toBe("rare");
    expect(caught.slice(2, 5).map((s) => s.ball?.wild?.strain)).toEqual([1, 2, 3]);
    expect(caught.slice(2, 6).every((s) => s.fx?.wild === "struggle")).toBe(true);
    expect(caught[6]!.float!.text).toBe("Caught!");

    const free = stepsFor([{ type: "capture_attempt", side: "player", emblem: "common", chance: 0.58, success: false }]);
    expect(free.map((s) => s.ball?.wild?.phase)).toEqual(["throw", "throw", "wobble", "wobble", "wobble", "still", "open"]);
    expect(free[6]!.fx).toEqual({ wild: "release" });
  });

  it("shows no effect for a catch that does nothing and ignores events without a picture", () => {
    expect(stepsFor([{ type: "catch_ignored", side: "wild" }])[0]!.float!.text).toBe("No effect");
    expect(stepsFor([{ type: "order", first: "player" }, { type: "mystery", side: "player" }])).toEqual([]);
  });
});
