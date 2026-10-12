import type { BattleEvent, Side } from "../api/AscensionClient";
import { titleCase } from "./ascension";

/** What one fighter's picture does during a step. */
export type Fx = "lunge" | "hit" | "guarded" | "guard" | "boost" | "flee-away" | "flee-fail" | "absorb" | "release";
/** Where a thrown EMBLEM is on its way to the wild Ascended: thrown, shaken by the Ascended
 * fighting it (`strain` 1 to 3, harder each time), a held breath, then closed or broken open. */
export type BallPhase = "throw" | "wobble" | "still" | "caught" | "open";
export type FloatTone = "damage" | "guarded" | "good" | "bad" | "info";

export interface Ball {
  phase: BallPhase;
  emblem: string;
  strain?: 1 | 2 | 3;
}

export interface Floating {
  side: Side;
  text: string;
  tone: FloatTone;
}

/** One beat of a round's playback: what each side shows for `ms`, and the health that is
 * true once it lands. */
export interface Step {
  ms: number;
  fx?: Partial<Record<Side, Fx>>;
  ball?: Partial<Record<Side, Ball>>;
  float?: Floating;
  hp?: { side: Side; value: number };
}

export const other = (side: Side): Side => (side === "player" ? "wild" : "player");

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stepsForEvent(event: BattleEvent): Step[] {
  const side = event.side;
  if (side !== "player" && side !== "wild") return [];
  const target = other(side);
  switch (event.type) {
    case "attack": {
      const guarded = event.protected === true;
      return [
        { ms: 320, fx: { [side]: "lunge" } },
        {
          ms: 460,
          fx: { [target]: guarded ? "guarded" : "hit" },
          float: { side: target, text: `-${num(event.damage)}`, tone: guarded ? "guarded" : "damage" },
          hp: { side: target, value: num(event.target_hp) },
        },
      ];
    }
    case "defense":
      return [{ ms: 700, fx: { [side]: "guard" }, float: { side, text: "Guard up", tone: "info" } }];
    case "support":
      return [
        { ms: 700, fx: { [side]: "boost" }, float: { side, text: `+${num(event.amount)} ${titleCase(String(event.stat))}`, tone: "good" } },
      ];
    case "flee":
      return event.success === true
        ? [{ ms: 800, fx: { [side]: "flee-away" }, float: { side, text: "Got away!", tone: "good" } }]
        : [{ ms: 600, fx: { [side]: "flee-fail" }, float: { side, text: "Can't escape!", tone: "bad" } }];
    case "catch_counters_flee":
      return [{ ms: 600, fx: { [target]: "flee-fail" }, float: { side: target, text: "Can't escape!", tone: "bad" } }];
    case "catch_ignored":
      return [{ ms: 600, float: { side, text: "No effect", tone: "info" } }];
    case "capture_attempt": {
      const emblem = String(event.emblem ?? "common");
      const caught = event.success === true;
      return [
        { ms: 650, ball: { [target]: { phase: "throw", emblem } } },
        { ms: 450, fx: { [target]: "absorb" }, ball: { [target]: { phase: "throw", emblem } } },
        { ms: 800, fx: { [target]: "absorb" }, ball: { [target]: { phase: "wobble", emblem, strain: 1 } } },
        { ms: 900, fx: { [target]: "absorb" }, ball: { [target]: { phase: "wobble", emblem, strain: 2 } } },
        { ms: 1000, fx: { [target]: "absorb" }, ball: { [target]: { phase: "wobble", emblem, strain: 3 } } },
        { ms: 600, fx: { [target]: "absorb" }, ball: { [target]: { phase: "still", emblem } } },
        caught
          ? { ms: 800, fx: { [target]: "absorb" }, ball: { [target]: { phase: "caught", emblem } }, float: { side: target, text: "Caught!", tone: "good" } }
          : { ms: 700, fx: { [target]: "release" }, ball: { [target]: { phase: "open", emblem } }, float: { side: target, text: "Broke free!", tone: "bad" } },
      ];
    }
    default:
      return [];
  }
}

/** A round's events as playback steps, in the order the server reported them. */
export function stepsFor(events: readonly BattleEvent[]): Step[] {
  return events.flatMap(stepsForEvent);
}
