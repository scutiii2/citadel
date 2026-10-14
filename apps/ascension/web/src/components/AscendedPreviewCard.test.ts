import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ascendedInfo } from "../api/AscensionClient.fixtures";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
describe("AscendedPreviewCard", () => {
  it("shows name, optional stars and optional level, with the frame in the tier colour", () => {
    const plain = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), tierId: "royal" } });
    expect(plain.find(".ascended-name").text()).toBe("Striker");
    expect(plain.find(".stars").exists()).toBe(false);
    expect(plain.attributes("style")).toContain("--em-tier-royal");
    const starred = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), stars: 3 } });
    expect(starred.find(".stars").text()).toBe("★ 3");
    expect(plain.find(".level").exists()).toBe(false);
    const leveled = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), level: 7, showLevel: true } });
    expect(leveled.find(".level").text()).toBe("Lv 7");
  });
  it("shows HP, Power and Speed over the art when stats are given", () => {
    const none = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker") } });
    expect(none.find(".stats").exists()).toBe(false);
    const card = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("striker"), stats: [{ key: "hp", label: "HP", value: 648 }, { key: "power", label: "Power", value: 64 }, { key: "speed", label: "Speed", value: 36 }] } });
    expect(card.find(".art .stats").text()).toBe("HP648Power64Speed36");
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
    expect(one.find(".front-types img").attributes("src")).toBe("/assets/types/enchant.webp");
    const two = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("x", { ascension_types: ["enchant", "divine"] }) } });
    expect(two.findAll(".front-types img").map(s => s.attributes("src"))).toEqual(["/assets/types/enchant_flat.webp", "/assets/types/divine_flat.webp"]);
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
  it.each(["common", "rare", "unique", "royal", "legendary", "forbidden"])("uses the %s WebP frame and matching back", (tierId) => {
    const front = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("guardian"), tierId } });
    expect(front.find("img.tier-frame").attributes("src")).toContain(`frame_${tierId}.webp`);
    const back = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("guardian"), tierId, flipped: true } });
    expect(back.find("img.tier-back").attributes("src")).toContain(`back_${tierId}.webp`);
    expect(back.find(".type-symbol").exists()).toBe(false);
    expect(back.find(".front-types").exists()).toBe(false);
    expect(back.find(".unknown").text()).toBe("UNCOLLECTED");
  });
  it("falls back to Common artwork for an unknown tier", () => {
    const card = mount(AscendedPreviewCard, { props: { ascended: ascendedInfo("guardian"), tierId: "unknown" } });
    expect(card.find("img.tier-frame").attributes("src")).toContain("frame_common.webp");
  });
});
