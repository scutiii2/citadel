import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ascendedInfo } from "../api/AscensionClient.fixtures";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";

describe("AscendedPreviewCard", () => {
  it("shows the name on the front and the level only when asked", () => {
    const plain = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker") } });
    expect(plain.find(".ascended-name").text()).toBe("Striker");
    expect(plain.find(".level").exists()).toBe(false);

    const leveled = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), level: 7, showLevel: true } });
    expect(leveled.find(".level").text()).toBe("Lv 7");
  });

  it("names the tier for assistive tech and draws it only as the frame's colour", () => {
    const wrapper = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), level: 3, tierId: "royal" } });

    expect(wrapper.attributes("aria-label")).toBe("Striker, Royal, level 3");
    expect(wrapper.text()).not.toContain("Royal");
    const [front, back] = wrapper.findAll("img.frame").map((img) => img.attributes("src"));
    expect(front).toContain("front_royal");
    expect(back).toContain("back_royal");
  });

  it("uses a different frame for every tier and falls back to Common for an unknown one", () => {
    const frames = (tierId: string) =>
      mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), tierId } })
        .findAll("img.frame")
        .map((img) => img.attributes("src"));
    const tiers = ["common", "rare", "unique", "royal", "legendary", "forbidden"];

    expect(new Set(tiers.flatMap(frames)).size).toBe(12);
    expect(frames("mystery")).toEqual(frames("common"));
  });

  it("puts the preview sprite in the window, or the first letter when there is none", () => {
    const sentinel = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("sentinel") } });
    expect(sentinel.find("img.portrait").attributes("src")).toBe("/ascended/sentinel/sprite_preview_card.webp");
    expect(sentinel.find(".letter").exists()).toBe(false);

    const bruiser = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("bruiser") } });
    expect(bruiser.find("img.portrait").exists()).toBe(false);
    expect(bruiser.find(".letter").text()).toBe("B");
  });

  it("shows every Ascension Type on the back, smaller when they share the medallion", () => {
    const symbols = (types: string[]) =>
      mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("x", { ascension_types: types }) } }).findAll(".back img.type-symbol");

    expect(symbols([])).toHaveLength(0);
    const one = symbols(["enchant"]);
    expect(one).toHaveLength(1);
    expect(one[0]!.attributes("src")).toBe("/assets/types/enchant.webp");
    const two = symbols(["enchant", "divine"]);
    expect(two.map((s) => s.attributes("src"))).toEqual(["/assets/types/enchant_flat.webp", "/assets/types/divine_flat.webp"]);
    expect((two[0]!.element as HTMLElement).style.width).not.toBe((one[0]!.element as HTMLElement).style.width);
  });

  it("can be turned to its back", () => {
    expect(mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("x") } }).classes()).not.toContain("flipped");
    expect(mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("x"), flipped: true } }).classes()).toContain("flipped");
  });
});
