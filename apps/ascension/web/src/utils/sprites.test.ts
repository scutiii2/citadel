import { describe, expect, it } from "vitest";
import type { AscendedArtInfo } from "../api/AscensionClient";
import { poseFor, spriteFocus, spriteFor } from "./sprites";
const ART: AscendedArtInfo = { main_card: "/a/main.webp", preview_card: "/a/preview.webp", battle: "/a/battle.webp", focus: 21, focus_preview: 50, animation: null };
describe("spriteFor", () => {
  it("uses battle art for every display", () => {
    for (const slot of ["main_card", "preview_card", "battle"] as const) expect(spriteFor(ART, slot)).toBe("/a/battle.webp");
  });
  it("never reveals legacy portraits when battle art is absent", () => {
    for (const slot of ["main_card", "preview_card", "battle"] as const) expect(spriteFor({ ...ART, battle: null }, slot)).toBeNull();
    expect(spriteFor(undefined, "battle")).toBeNull();
  });
});
describe("spriteFocus", () => {
  it("preserves legacy crop metadata for callers that request it", () => {
    expect(spriteFocus(ART, "main_card")).toBe(21);
    expect(spriteFocus(ART, "preview_card")).toBe(50);
    expect(spriteFocus(undefined, "main_card")).toBe(50);
  });
});
describe("poseFor", () => {
  it("maps battle cues to animation states", () => {
    expect(poseFor("lunge", false)).toBe("attack");
    expect(poseFor("guard", false)).toBe("defend");
    expect(poseFor("boost", false)).toBe("support");
    expect(poseFor("flee-away", false)).toBe("flee");
    expect(poseFor("flee-fail", false)).toBe("flee");
    expect(poseFor(null, false)).toBe("idle");
    expect(poseFor(null, true)).toBe("catch");
  });
});
