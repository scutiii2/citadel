import type { AscendedArtInfo } from "../api/AscensionClient";

export type SpriteSlot = "main_card" | "preview_card" | "battle";

const FALLBACK_ORDER: SpriteSlot[] = ["main_card", "preview_card", "battle"];

/** The picture for a slot: its own sprite, else the first one that exists, else null (the letter placeholder). */
export function spriteFor(art: AscendedArtInfo | undefined, slot: SpriteSlot): string | null {
  if (!art) return null;
  return art[slot] ?? FALLBACK_ORDER.map((name) => art[name]).find((url) => url !== null) ?? null;
}

/** Where to centre the crop for a slot, in percent. */
export function spriteFocus(art: AscendedArtInfo | undefined, slot: SpriteSlot): number {
  return (slot === "preview_card" ? art?.focus_preview : art?.focus) ?? 50;
}
