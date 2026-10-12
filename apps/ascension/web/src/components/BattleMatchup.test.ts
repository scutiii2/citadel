import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ENCOUNTER, ascendedInfo, ownedAscended } from "../api/AscensionClient.fixtures";
import BattleMatchup from "./BattleMatchup.vue";

const props = () => ({
  player: ownedAscended("guardian", { level: 5, tier_id: "rare" }),
  playerInfo: ascendedInfo("guardian"),
  wild: ENCOUNTER,
  wildInfo: ascendedInfo("bruiser"),
  playerMultiplier: 1.6,
});

describe("BattleMatchup", () => {
  it("shows both fighters, their own tiers and levels, and current player stats", () => {
    const wrapper = mount(BattleMatchup, { props: props() });
    expect(wrapper.find(".player .ascended-name").text()).toBe("Guardian");
    expect(wrapper.find(".wild .ascended-name").text()).toBe("Bruiser");
    expect(wrapper.find(".player").text()).toContain("Level 5");
    expect(wrapper.find(".wild").text()).toContain("Level 4");
    expect(wrapper.find(".player .em-tier").text()).toBe("Rare");
    expect(wrapper.findAll(".stats dd").map(s => s.text())).toEqual(["192", "22", "22"]);
    expect(wrapper.text()).toContain("Opponent personalities stay hidden until capture");
  });

  it("uses the catalog crop and falls back to a letter when artwork is missing or fails", async () => {
    const setup = props();
    setup.playerInfo.art!.focus = 21;
    const wrapper = mount(BattleMatchup, { props: setup });
    expect(wrapper.find(".player img").attributes("src")).toBe("/ascended/guardian/sprite_main_card.webp");
    expect(wrapper.find(".player img").attributes("style")).toContain("50% 21%");
    expect(wrapper.find(".wild .letter").text()).toBe("B");
    await wrapper.find(".player img").trigger("error");
    expect(wrapper.find(".player img").exists()).toBe(false);
    expect(wrapper.find(".player .letter").text()).toBe("G");
  });

  it("does not invent a fighter or stats when no ready member is selected", () => {
    const wrapper = mount(BattleMatchup, { props: { ...props(), player: null, playerInfo: null } });
    expect(wrapper.find(".player").text()).toContain("Choose a fighter");
    expect(wrapper.find(".stats").exists()).toBe(false);
    expect(wrapper.find(".wild .ascended-name").text()).toBe("Bruiser");
  });
});
