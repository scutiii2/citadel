import { defineStore } from "pinia";
import { ref, watch } from "vue";
import type { Side } from "../api/AscensionClient";
import { stepsFor, type Ball, type Floating, type Fx, type Step } from "../utils/battleCues";
import { useAscensionStore } from "./ascension";

/** More waiting steps than this and the rest play at half length, so a backlog catches up. */
const BACKLOG_STEPS = 8;

const idle = <T>(): Record<Side, T | null> => ({ player: null, wild: null });

/** Plays each new round of the battle as a short animation, one step at a time, and says
 * what the arena should show meanwhile: each fighter's effect, a thrown EMBLEM, a floating
 * text, and the health to show (the old value until the hit lands). Nothing plays when a
 * battle is first opened or restored or when an EMBLEM prompt is open (its 5 seconds are
 * running). It plays even when the system asks for reduced motion: the battle is the game. `busy` stays true until the last
 * step ends, so the page can hold the result and the action buttons back. */
export const usePlaybackStore = defineStore("playback", () => {
  const ascension = useAscensionStore();

  const busy = ref(false);
  const fx = ref<Record<Side, Fx | null>>(idle());
  const ball = ref<Record<Side, Ball | null>>(idle());
  const floating = ref<Floating & { id: number } | null>(null);
  /** Health to show while playing; null shows the real one. */
  const hp = ref<Partial<Record<Side, number>> | null>(null);

  let queue: Step[] = [];
  let runId = 0;
  let floatId = 0;
  let wake: (() => void) | null = null;

  function wait(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const timer = setTimeout(done, ms);
      wake = done;
      function done(): void {
        clearTimeout(timer);
        wake = null;
        resolve();
      }
    });
  }

  function clear(): void {
    fx.value = idle();
    ball.value = idle();
    floating.value = null;
    hp.value = null;
    busy.value = false;
  }

  function show(step: Step): void {
    fx.value = { ...idle<Fx>(), ...step.fx };
    ball.value = { ...idle<Ball>(), ...step.ball };
    floating.value = step.float ? { ...step.float, id: (floatId += 1) } : null;
    if (step.hp) hp.value = { ...hp.value, [step.hp.side]: step.hp.value };
  }

  async function run(): Promise<void> {
    const id = (runId += 1);
    busy.value = true;
    while (queue.length > 0 && id === runId) {
      const step = queue.shift()!;
      show(step);
      await wait(queue.length > BACKLOG_STEPS ? step.ms / 2 : step.ms);
    }
    if (id === runId) clear();
  }

  /** Jumps to the end: the real health shows and the result may open. */
  function skip(): void {
    queue = [];
    wake?.();
  }

  function reset(): void {
    runId += 1;
    queue = [];
    wake?.();
    clear();
  }

  watch(
    () => ascension.battle,
    (now, before) => {
      if (now === null || before === null || now.id !== before.id) {
        reset();
        return;
      }
      if (now.phase === "awaiting_emblem") {
        reset();
        return;
      }
      const fresh = now.history.slice(before.history.length);
      if (fresh.length === 0) return;
      const steps = fresh.flatMap((round) => stepsFor(round.events));
      if (steps.length === 0) return;
      const starting = !busy.value;
      if (starting) hp.value = { player: before.player.hp, wild: before.wild.hp };
      queue.push(...steps);
      if (starting) void run();
    },
  );

  return { busy, fx, ball, floating, hp, skip };
});
