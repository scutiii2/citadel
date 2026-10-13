import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient } from "../api/AscensionClient";
import { CATALOG, PROFILE } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "../stores/ascension";
import StarterPick from "./StarterPick.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { createProfile: vi.fn() };
  return { useAscensionClient: () => client };
});

const client = vi.mocked(useAscensionClient());

beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  useAscensionStore().catalog = CATALOG;
});

describe("StarterPick", () => {
  it("lists the starters as preview cards with stats and selects the first", () => {
    const wrapper = mount(StarterPick);

    const choices = wrapper.findAll("[role=radio]");
    expect(choices.map((c) => c.attributes("aria-label"))).toEqual(["Guardian", "Striker"]);
    expect(choices.map((c) => c.attributes("aria-checked"))).toEqual(["true", "false"]);
    expect(choices[0]!.classes()).toContain("selected");
    expect(choices.every((c) => c.classes().includes("em-lift"))).toBe(true);
    expect(wrapper.findAll(".card .ascended-name").map((n) => n.text())).toEqual(["Guardian", "Striker"]);
    expect(wrapper.find(".card .stats").exists()).toBe(true);
    expect(wrapper.find(".card .stars").text()).toBe("★ 0");
    expect(wrapper.find(".card .level").text()).toBe("Lv 1");
    expect(wrapper.find(".starter-inspector").exists()).toBe(false);
    expect(wrapper.find("button.start").text()).toBe("Start with Guardian");
  });

  it("picking a card selects it and starts with it", async () => {
    client.createProfile.mockResolvedValue(PROFILE);
    const wrapper = mount(StarterPick);

    await wrapper.findAll("[role=radio]")[1]!.trigger("click");
    expect(wrapper.findAll("[role=radio]").map((c) => c.classes().includes("selected"))).toEqual([false, true]);
    expect(client.createProfile).not.toHaveBeenCalled();

    await wrapper.find("button.start").trigger("click");
    await flushPromises();

    expect(client.createProfile).toHaveBeenCalledExactlyOnceWith("striker");
    expect(wrapper.emitted("started")).toHaveLength(1);
  });

  it("starts with the first starter when none was clicked, and picks by keyboard", async () => {
    client.createProfile.mockResolvedValue(PROFILE);
    const wrapper = mount(StarterPick);

    await wrapper.findAll("[role=radio]")[1]!.trigger("keydown.enter");
    expect(wrapper.find("button.start").text()).toBe("Start with Striker");
    await wrapper.findAll("[role=radio]")[0]!.trigger("keydown.space");
    await wrapper.find("button.start").trigger("click");
    await flushPromises();

    expect(client.createProfile).toHaveBeenCalledExactlyOnceWith("guardian");
  });

  it("has no side panel, only the start button for the chosen starter", async () => {
    const wrapper = mount(StarterPick);

    expect(wrapper.find(".info").exists()).toBe(false);
    expect(wrapper.find(".back-link").exists()).toBe(false);
    expect(wrapper.find("button.start").text()).toBe("Start with Guardian");
    await wrapper.findAll("[role=radio]")[1]!.trigger("click");
    expect(wrapper.find("button.start").text()).toBe("Start with Striker");
    expect(wrapper.findAll("[role=radio].selected")).toHaveLength(1);
  });

  it("goes back to the menu", async () => {
    const wrapper = mount(StarterPick);
    await wrapper.find("button.back").trigger("click");

    expect(wrapper.emitted("back")).toHaveLength(1);
  });
});
