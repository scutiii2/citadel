import type { AnimationState, AscendedArtInfo } from "../api/AscensionClient";
import type { Fx } from "./battleCues";

export type SpriteSlot = "main_card" | "preview_card" | "battle";

/** Every display uses battle art; legacy portraits remain preserved on disk. */
export function spriteFor(art: AscendedArtInfo | undefined, _slot: SpriteSlot): string | null {
  return art?.battle ?? null;
}

/** Where to centre the crop for a slot, in percent. */
export function spriteFocus(art: AscendedArtInfo | undefined, slot: SpriteSlot): number {
  return (slot === "preview_card" ? art?.focus_preview : art?.focus) ?? 50;
}

/** The animation state a fighter shows: what its effect or an incoming EMBLEM throw (it catches) asks for, else idle.
 * Being hit has no frames of its own; the arena shakes the idle picture. */
export function poseFor(fx: Fx | null | undefined, catching: boolean): AnimationState {
  if (catching) return "catch";
  switch (fx) {
    case "lunge": return "attack";
    case "guard": return "defend";
    case "boost": return "support";
    case "flee-away":
    case "flee-fail": return "flee";
    default: return "idle";
  }
}
