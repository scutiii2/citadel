import { describe, expect, it } from "vitest";
import type { AscendedArtInfo } from "../api/AscensionClient";
import { poseFor, spriteFocus, spriteFor } from "./sprites";

const ART: AscendedArtInfo = { main_card: "/a/main.webp", preview_card: "/a/preview.webp", battle: "/a/battle.webp", focus: 21, focus_preview: 50, animation: null };

describe("spriteFor", () => {
  it("gives the slot's own sprite", () => {
    expect(spriteFor(ART, "main_card")).toBe("/a/main.webp");
    expect(spriteFor(ART, "preview_card")).toBe("/a/preview.webp");
    expect(spriteFor(ART, "battle")).toBe("/a/battle.webp");
  });

  it("falls back to the first sprite that exists, in the order main, preview, battle", () => {
    expect(spriteFor({ ...ART, battle: null }, "battle")).toBe("/a/main.webp");
    expect(spriteFor({ ...ART, main_card: null, battle: null }, "battle")).toBe("/a/preview.webp");
    expect(spriteFor({ ...ART, main_card: null, preview_card: null }, "main_card")).toBe("/a/battle.webp");
  });

  it("is null when there is no sprite at all or no art", () => {
    expect(spriteFor({ ...ART, main_card: null, preview_card: null, battle: null }, "battle")).toBeNull();
    expect(spriteFor(undefined, "battle")).toBeNull();
  });
});

describe("spriteFocus", () => {
  it("uses focus for the main card, focus_preview for the preview card, 50 when unknown", () => {
    expect(spriteFocus({ ...ART, focus: 21, focus_preview: 14 }, "main_card")).toBe(21);
    expect(spriteFocus({ ...ART, focus: 21, focus_preview: 14 }, "preview_card")).toBe(14);
    expect(spriteFocus(undefined, "main_card")).toBe(50);
  });
});

describe("poseFor", () => {
  it("maps what a fighter does to its animation state, idle otherwise", () => {
    expect(poseFor("lunge", false)).toBe("attack");
    expect(poseFor("guard", false)).toBe("defend");
    expect(poseFor("boost", false)).toBe("support");
    expect(poseFor("flee-away", false)).toBe("flee");
    expect(poseFor("flee-fail", false)).toBe("flee");
    for (const fx of ["hit", "guarded", "absorb", "release", null, undefined] as const) expect(poseFor(fx, false)).toBe("idle");
  });

  it("catches while an EMBLEM is thrown at the other side", () => {
    expect(poseFor(null, true)).toBe("catch");
  });
});
