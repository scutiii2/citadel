import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient } from "./api/AscensionClient";
import { CATALOG, PROFILE, battleView } from "./api/AscensionClient.fixtures";
import { ApiError } from "./api/http";
import { useSessionStore } from "./stores/session";
import AscensionView from "./App.vue";

vi.mock("./api/AscensionClient", () => {
  const client = {
    catalog: vi.fn(),
    profile: vi.fn(),
    createProfile: vi.fn(),
    battle: vi.fn(),
    encounter: vi.fn(),
    personalities: vi.fn(),
    preset: vi.fn(),
    advance: vi.fn(),
    shop: vi.fn(),
    resetProfile: vi.fn(),
  };
  return { useAscensionClient: () => client };
});

const client = vi.mocked(useAscensionClient());

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

beforeEach(() => {
  vi.resetAllMocks();
  client.catalog.mockResolvedValue(CATALOG);
  client.profile.mockResolvedValue(PROFILE);
  client.personalities.mockResolvedValue({ items: [], next_cursor: null });
  client.preset.mockResolvedValue({ ascended_id: "guardian", slot: 1, instance_ids: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

async function mountView() {
  setActivePinia(createPinia());
  useSessionStore().status = "ready";
  const wrapper = mount(AscensionView);
  await flushPromises();
  return wrapper;
}

type Wrapper = Awaited<ReturnType<typeof mountView>>;
const tab = (wrapper: Wrapper, label: string) => wrapper.findAll("[role=tab]").find((b) => b.text() === label)!;

describe("AscensionView", () => {
  it("a first visit opens the menu, then New game picks a starter and opens the collection", async () => {
    client.profile.mockRejectedValue(new ApiError(404, "no profile yet; choose a starter first"));
    const wrapper = await mountView();

    expect(wrapper.find("[role=tab]").exists()).toBe(false);
    expect(wrapper.findAll("nav .label").map((t) => t.text())).toEqual(["New game", "How to play"]);

    await wrapper.find("button.primary").trigger("click");
    expect(wrapper.text()).toContain("Choose your first Ascended");
    expect(wrapper.findAll("[role=radio]").map((c) => c.attributes("aria-label"))).toEqual(["Guardian", "Striker"]);

    client.createProfile.mockResolvedValue(PROFILE);
    await wrapper.findAll("[role=radio]")[0]!.trigger("click");
    await wrapper.find("button.start").trigger("click");
    await flushPromises();

    expect(client.createProfile).toHaveBeenCalledExactlyOnceWith("guardian");
    expect(wrapper.findAll(".squad-card")).toHaveLength(1);
    expect(tab(wrapper, "Collection").classes()).toContain("active");
  });

  it("opens the collection directly for returning players and uses Insignia to open the shop", async () => {
    const wrapper = await mountView();
    expect(tab(wrapper, "Collection").classes()).toContain("active");
    expect(wrapper.find(".hero").exists()).toBe(false);
    expect(wrapper.find("button.menu-link").exists()).toBe(false);
    expect(wrapper.findAll(".navigation [role=tab]").map(t => t.text())).toEqual(["Battle", "Collection"]);
    await wrapper.find("button.wallet").trigger("click");
    await flushPromises();
    expect(wrapper.find(".shop").exists()).toBe(true);
    expect(wrapper.find("button.wallet").attributes("aria-pressed")).toBe("true");
    await tab(wrapper, "Collection").trigger("click");
    expect(wrapper.find(".collection").exists()).toBe(true);
    wrapper.unmount();
  });

  it("opens help and settings from the header and resets only after confirmation", async () => {
    client.resetProfile.mockResolvedValue({ reset: true });
    const wrapper = await mountView();
    await wrapper.find('[aria-label="How to play"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('dialog[aria-label="Keep the fire going"]').attributes("open")).toBeDefined();
    await wrapper.find('dialog[aria-label="Keep the fire going"] button.close').trigger("click");
    await wrapper.find('[aria-label="Settings"]').trigger("click");
    await flushPromises();
    const settings = wrapper.find('dialog[aria-label="Settings"]');
    expect(settings.attributes("open")).toBeDefined();
    await settings.find("button.danger").trigger("click");
    await flushPromises();
    const confirmation = wrapper.find('dialog[aria-label="Reset all Ascension progress?"]');
    expect((confirmation.find("button.confirm").element as HTMLButtonElement).disabled).toBe(true);
    expect(client.resetProfile).not.toHaveBeenCalled();
    await confirmation.find("input").setValue("RESET");
    await confirmation.find("button.confirm").trigger("click");
    await flushPromises();
    expect(client.resetProfile).toHaveBeenCalledTimes(1);
    expect(wrapper.find(".hero").exists()).toBe(true);
    expect(wrapper.find('button[aria-label="Settings"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("prevents reset from settings while a battle is active", async () => {
    client.profile.mockResolvedValue({ ...PROFILE, active_battle: "b1" });
    client.battle.mockResolvedValue(battleView({ mode: "manual" }));
    const wrapper = await mountView();
    await wrapper.find('[aria-label="Settings"]').trigger("click");
    await flushPromises();
    const settings = wrapper.find('dialog[aria-label="Settings"]');
    expect((settings.find("button.danger").element as HTMLButtonElement).disabled).toBe(true);
    expect(settings.text()).toContain("Finish or forfeit your battle to reset");
    wrapper.unmount();
  });

  it("shows Insignia in the masthead and a title for each tab", async () => {
    const wrapper = await mountView();

    expect(wrapper.find(".wallet").text()).toBe("100 Insignia");
    expect(wrapper.find(".subtitle").text()).toBe("1 Ascended. Every one has a story.");

    await tab(wrapper, "Battle").trigger("click");
    expect(wrapper.find("h2").text()).toBe("Into the wild");
    expect(wrapper.find(".subtitle").text()).toBe("Your next Ascended is waiting.");
  });

  it("restores an active battle on the Battle tab instead of rolling", async () => {
    client.profile.mockResolvedValue({ ...PROFILE, active_battle: "b1" });
    client.battle.mockResolvedValue(battleView({ mode: "manual" }));
    const wrapper = await mountView();

    expect(tab(wrapper, "Battle").classes()).toContain("active");
    expect(wrapper.find(".arena").exists()).toBe(true);
    expect(wrapper.find(".action-bar").exists()).toBe(true);
  });

  it("replaces the page with a Retry when Ascension is unavailable", async () => {
    client.catalog.mockRejectedValueOnce(new ApiError(502, "Ascension is not available right now"));
    const wrapper = await mountView();

    expect(wrapper.find(".unavailable").text()).toContain("Ascension is not available right now");
    expect(wrapper.find("nav").exists()).toBe(false);

    await wrapper.find(".unavailable button").trigger("click");
    await flushPromises();

    expect(wrapper.find(".unavailable").exists()).toBe(false);
    expect(wrapper.find(".collection").exists()).toBe(true);
  });

  it("stops the battle loop when the page goes away", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "performance"] });
    client.profile.mockResolvedValue({ ...PROFILE, active_battle: "b1" });
    client.battle.mockResolvedValue(battleView());
    const wrapper = await mountView();

    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(client.advance).not.toHaveBeenCalled();
  });
});

describe("host session screen", () => {
  it("asks standalone visitors to open the game from Ember without loading a save", async () => {
    setActivePinia(createPinia());
    const wrapper = mount(AscensionView);
    await flushPromises();
    expect(wrapper.text()).toContain("Open this game from Ember");
    expect(client.catalog).not.toHaveBeenCalled();
    expect(client.profile).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it("ends the game when its bearer session expires and stops the battle loop", async () => {
    const wrapper = await mountView();
    useSessionStore().end();
    await flushPromises();
    expect(wrapper.text()).toContain("Session ended, reopen the game from Ember");
    expect(wrapper.find("nav").exists()).toBe(false);
    wrapper.unmount();
  });
});
