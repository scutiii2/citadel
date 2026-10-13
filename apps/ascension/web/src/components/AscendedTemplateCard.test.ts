import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ascendedInfo } from "../api/AscensionClient.fixtures";
import AscendedTemplateCard from "./AscendedTemplateCard.vue";

const striker = ascendedInfo("striker", {
  base: { hp: 100, power: 30, speed: 20 },
  growth: { hp: 10, power: 3, speed: 2 },
  passive: { kind: "low_hp_attack_bonus", params: { hp_below: 0.5, power_fraction: 0.2 } },
});

describe("AscendedTemplateCard", () => {
  it("lays the name, level, stats, passive and abilities over the frame", () => {
    const wrapper = mount(AscendedTemplateCard, { props: { ascended: striker } });

    expect(wrapper.find(".ascended-name").text()).toBe("Striker");
    expect(wrapper.find(".level").text()).toBe("Lv 1");
    expect(wrapper.findAll(".stat").map((s) => s.text())).toEqual([
      expect.stringMatching(/HP\s*100\s*\+10 \/ lvl/),
      expect.stringMatching(/Power\s*30\s*\+3 \/ lvl/),
      expect.stringMatching(/Speed\s*20\s*\+2 \/ lvl/),
    ]);
    expect(wrapper.find(".passive strong").text()).toBe("Low hp attack bonus");
    expect(wrapper.find(".passive").text()).toBe("Low hp attack bonus Below 50% HP, attacks deal extra damage equal to 20% of its Power.");
    const abilities = wrapper.findAll(".ability");
    expect(abilities).toHaveLength(2);
    expect(abilities[0]!.text()).toContain("Strike");
    expect(abilities[0]!.text()).toContain("Attack 120% · cd 1");
    expect(abilities[1]!.find(".unlock").text()).toBe("Lv 5");
  });

  it("shows the level it is given and names the tier for assistive tech", () => {
    const wrapper = mount(AscendedTemplateCard, { props: { ascended: striker, level: 7, tierId: "rare" } });

    expect(wrapper.find(".level").text()).toBe("Lv 7");
    expect(wrapper.attributes("aria-label")).toBe("Striker, Rare, level 7");
  });

  it("keeps the passive's name and sentence in its tooltip, since the box cuts after four lines", () => {
    const wrapper = mount(AscendedTemplateCard, { props: { ascended: striker } });

    expect(wrapper.find(".passive").attributes("title")).toBe(
      "Low hp attack bonus: Below 50% HP, attacks deal extra damage equal to 20% of its Power.",
    );
  });

  it("falls back to the passive's name for a kind it has no sentence for", () => {
    const wrapper = mount(AscendedTemplateCard, { props: { ascended: ascendedInfo("odd") } });

    expect(wrapper.find(".passive").text()).toBe("Steady");
  });

  it("names its tier for assistive tech and uses battle artwork", () => {
    const card = mount(AscendedTemplateCard, { props: { ascended: ascendedInfo("guardian"), tierId: "rare" } });
    expect(card.attributes("aria-label")).toBe("Guardian, Rare, level 1");
    expect(card.find("img.portrait").attributes("src")).toBe("/ascended/guardian/sprite_battle.webp");
  });
});
