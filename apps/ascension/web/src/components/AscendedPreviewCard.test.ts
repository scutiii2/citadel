import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ascendedInfo } from "../api/AscensionClient.fixtures";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
describe("AscendedPreviewCard", () => {
  it("shows name, readable tier and optional level", () => {
    const plain = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), tierId: "royal" } });
    expect(plain.find(".ascended-name").text()).toBe("Striker");
    expect(plain.find(".tier").text()).toBe("Royal");
    expect(plain.find(".level").exists()).toBe(false);
    const leveled = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), level: 7, showLevel: true } });
    expect(leveled.find(".level").text()).toBe("Lv 7");
  });
  it("uses battle art or a letter placeholder", () => {
    const card = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("sentinel") } });
    expect(card.find("img.portrait").attributes("src")).toBe("/ascended/sentinel/sprite_battle.webp");
    const missing = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("bruiser") } });
    expect(missing.find("img.portrait").exists()).toBe(false);
    expect(missing.find(".letter").text()).toBe("B");
  });
  it("preserves detailed and flat type symbols", () => {
    const one = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("x", { ascension_types: ["enchant"] }) } });
    expect(one.find(".types img").attributes("src")).toBe("/assets/types/enchant.webp");
    const two = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("x", { ascension_types: ["enchant", "divine"] }) } });
    expect(two.findAll(".types img").map(s => s.attributes("src"))).toEqual(["/assets/types/enchant_flat.webp", "/assets/types/divine_flat.webp"]);
  });
  it("conceals character artwork and name when uncollected", () => {
    const card = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("guardian"), flipped: true } });
    expect(card.classes()).toContain("flipped");
    expect(card.find("img.portrait").exists()).toBe(false);
    expect(card.attributes("aria-label")).toBe("Uncollected Ascended");
  });
  it("keeps caller back classes separate from the concealed card face", () => {
    const card = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("guardian"), flipped: true }, attrs: { class: "back" } });
    expect(card.classes()).toContain("back");
    expect(card.find(".card-back.concealed").exists()).toBe(true);
    expect(card.find("img.portrait").exists()).toBe(false);
  });
});
