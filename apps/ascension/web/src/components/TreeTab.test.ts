import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAscensionClient, type TreeView } from "../api/AscensionClient";
import { CATALOG, PROFILE, ownedAscended } from "../api/AscensionClient.fixtures";
import { useAscensionStore } from "../stores/ascension";
import TreeTab from "./TreeTab.vue";

vi.mock("../api/AscensionClient", () => {
  const client = { tree: vi.fn(), learnNode: vi.fn(), saveLoadout: vi.fn(), profile: vi.fn() };
  return { useAscensionClient: () => client };
});

const client = vi.mocked(useAscensionClient());

const node = (id: string, extra = {}) => ({
  id, kind: "ability" as const, name: id.replace("g_", "").toUpperCase(), x: 40, y: 40, requires: [], unlock_level: 1, root: false,
  cost: null, category: "ATTACK", percentage: 100, cooldown: 1, stat: null, duration: null, state: "learned" as const, reason: null, ...extra,
});

const TREE: TreeView = {
  ascended_id: "guardian", level: 12, essences: { common: 3 },
  slots: [{ id: "a1", kind: "ability", branches: null }, { id: "a2", kind: "ability", branches: null },
          { id: "a3", kind: "ability", branches: null }, { id: "p1", kind: "passive", branches: null }],
  nodes: [
    node("g_a", { root: true, x: 40, y: 40 }),
    node("g_b", { root: true, x: 40, y: 160, category: "DEFENSE" }),
    node("g_pass", { kind: "passive", root: true, x: 160, y: 100, passive: { kind: "none", params: {} } }),
    node("g_wall", { x: 200, y: 40, requires: ["g_a"], unlock_level: 12, cost: { tier: "common", amount: 3 }, state: "learnable" }),
    node("g_far", { x: 320, y: 40, requires: ["g_wall"], unlock_level: 20, cost: { tier: "rare", amount: 3 }, state: "locked", reason: "needs level 20" }),
  ],
  loadout: { a1: "g_a", a2: "g_b", a3: null, p1: "g_pass" },
};

beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  const store = useAscensionStore();
  store.catalog = CATALOG;
  store.profile = PROFILE;
  client.tree.mockResolvedValue(structuredClone(TREE));
  client.profile.mockResolvedValue(PROFILE);
});

const mountTab = async () => {
  const wrapper = mount(TreeTab, { props: { ascended: ownedAscended("guardian", { level: 12 }) } });
  await flushPromises();
  return wrapper;
};

describe("TreeTab", () => {
  it("centers the first successful load even after a failed initial request", async () => {
    client.tree.mockRejectedValueOnce(new Error("Try again"));
    const wrapper = await mountTab();
    const scrollTo = vi.fn();
    HTMLElement.prototype.scrollTo = scrollTo;
    try {
      await wrapper.findAll("button").find(b => b.text() === "Retry")!.trigger("click");
      await flushPromises();
      expect(scrollTo).toHaveBeenCalled();
    } finally {
      delete (HTMLElement.prototype as Partial<HTMLElement>).scrollTo;
    }
  });
  it("uses octagons for active abilities and circles for passives around a portrait hub", async () => {
    const wrapper = await mountTab();
    expect(wrapper.find(".origin-hub").text()).toContain("Guardian");
    expect(wrapper.find('[data-node="g_a"] polygon').exists()).toBe(true);
    expect(wrapper.find('[data-node="g_pass"] circle.node-outline').exists()).toBe(true);
    await wrapper.find('[data-node="g_far"]').trigger("click");
    expect(wrapper.findAll(".tree-line.highlighted")).toHaveLength(2);
    await wrapper.findAll("button").find(b => b.text() === "Hide names")!.trigger("click");
    expect(wrapper.find('[data-node="g_a"]').attributes('aria-label')).toContain('A');
    expect(wrapper.find('[data-node="g_a"] .node-name').isVisible()).toBe(false);
  });
  it("refreshes requirements after an upgrade consumes essence", async () => {
    const wrapper = await mountTab();
    const next = structuredClone(TREE);
    next.essences.common = 0;
    next.nodes[3] = { ...next.nodes[3]!, state: "locked", reason: "needs essence" };
    client.tree.mockResolvedValue(next);
    await wrapper.setProps({ ascended: ownedAscended("guardian", { level: 12, copies: 0, stars: 1 }) });
    await flushPromises();
    expect(client.tree).toHaveBeenCalledTimes(2);
    await wrapper.find('[data-node="g_wall"]').trigger("click");
    expect(wrapper.find(".node-detail").text()).toContain("You have 0");
    expect(wrapper.find(".node-detail button.learn").exists()).toBe(false);
  });
  it("shows an ability's effects in the node detail", async () => {
    const tree = structuredClone(TREE);
    tree.nodes[3] = { ...tree.nodes[3]!, effects: [{ kind: "bleed", percentage: 20, rounds: 3 }] };
    client.tree.mockResolvedValue(tree);
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_wall"]').trigger("click");

    expect(wrapper.find(".node-detail").text()).toContain("Bleeds 20% for 3 rounds");
  });
  it("draws every node at its place with its state and a line per prerequisite", async () => {
    const wrapper = await mountTab();

    expect(client.tree).toHaveBeenCalledWith("guardian");
    const nodes = wrapper.findAll(".tree-node");
    expect(nodes).toHaveLength(5);
    expect(wrapper.find('[data-node="g_wall"]').attributes("data-state")).toBe("learnable");
    expect(wrapper.find('[data-node="g_far"]').attributes("data-state")).toBe("locked");
    expect(wrapper.find('[data-node="g_wall"]').text()).toContain("Available");
    expect(wrapper.findAll(".tree-line")).toHaveLength(2);
    expect(wrapper.find(".slots").text()).toContain("empty");
  });

  it("shows individual unmet requirements and available essence in the inspector", async () => {
    const wrapper = await mountTab();
    await wrapper.find('[data-node="g_far"]').trigger("click");
    const detail = wrapper.find(".node-detail");
    expect(detail.text()).toContain("Level 20");
    expect(detail.text()).toContain("WALL");
    expect(detail.text()).toContain("You have 0");
    expect(wrapper.find('[data-node="g_far"]').text()).toContain("Locked");
  });

  it("learns a node and reloads the tree", async () => {
    client.learnNode.mockResolvedValue({ kind: "learn", ascended_id: "guardian", node_id: "g_wall", essence_tier: "common", essence_spent: 3 });
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_wall"]').trigger("click");
    expect(wrapper.find(".node-detail").text()).toContain("3 common essence");
    await wrapper.find(".node-detail button.learn").trigger("click");
    await flushPromises();

    expect(client.learnNode).toHaveBeenCalledWith("guardian", "g_wall");
    expect(client.tree).toHaveBeenCalledTimes(2);
  });

  it("shows why a locked node cannot be learned and disables Learn", async () => {
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_far"]').trigger("click");
    expect(wrapper.find(".node-detail").text()).toContain("needs level 20");
    expect(wrapper.find(".node-detail button.learn").exists()).toBe(false);
  });

  it("equips a learned ability in a slot and saves the whole loadout", async () => {
    client.saveLoadout.mockResolvedValue({ ascended_id: "guardian", slots: { a1: "g_b", p1: "g_pass" } });
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_b"]').trigger("click");
    await wrapper.find('.node-detail button[data-slot="a1"]').trigger("click");
    await flushPromises();

    expect(client.saveLoadout).toHaveBeenCalledWith("guardian", { a1: "g_b", a2: null, a3: null, p1: "g_pass" });
  });

  it("can unequip the passive", async () => {
    client.saveLoadout.mockResolvedValue({ ascended_id: "guardian", slots: { a1: "g_a", a2: "g_b" } });
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_pass"]').trigger("click");
    await wrapper.find(".node-detail button.unequip").trigger("click");
    await flushPromises();

    expect(client.saveLoadout).toHaveBeenCalledWith("guardian", { a1: "g_a", a2: "g_b", a3: null, p1: null });
  });

  it("shows why a learn failed inside the tab", async () => {
    client.learnNode.mockRejectedValue(new Error("Iron Wall needs 3 common essence"));
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_wall"]').trigger("click");
    await wrapper.find(".node-detail button.learn").trigger("click");
    await flushPromises();

    expect(wrapper.find(".tree-tab .em-notice").text()).toContain("Iron Wall needs 3 common essence");
  });

  it("describes a passive with its numbers", async () => {
    const tree = structuredClone(TREE);
    tree.nodes[2] = { ...tree.nodes[2]!, passive: { kind: "defense_rating_bonus", params: { power_fraction: 0.4 } } };
    client.tree.mockResolvedValue(tree);
    const wrapper = await mountTab();

    await wrapper.find('[data-node="g_pass"]').trigger("click");

    expect(wrapper.find(".node-detail").text()).toContain("Defense rating rises by 40% of its Power.");
  });

  it("shows six branch slots and only the matching equip buttons", async () => {
    const tree: TreeView = {
      ...structuredClone(TREE),
      slots: [
        { id: "a1", kind: "ability", branches: ["wolf"] },
        { id: "a2", kind: "ability", branches: ["bear"] },
        { id: "a3", kind: "ability", branches: ["dog"] },
        { id: "a4", kind: "ability", branches: ["aya"] },
        { id: "p1", kind: "passive", branches: ["wolf", "bear", "dog"] },
        { id: "p2", kind: "passive", branches: ["aya"] },
      ],
      nodes: [node("g_wolf", { branch: "wolf" }), node("g_aya", { kind: "passive", branch: "aya" })],
      loadout: { a1: "g_wolf", a2: null, a3: null, a4: null, p1: null, p2: null },
    };
    client.tree.mockResolvedValue(tree);
    client.saveLoadout.mockResolvedValue({ ascended_id: "guardian", slots: { a1: "g_wolf", p2: "g_aya" } });
    const wrapper = await mountTab();
    const chips = wrapper.findAll(".slots .slot");
    expect(chips).toHaveLength(6);
    expect(chips.map((chip) => chip.text())).toEqual([
      expect.stringContaining("wolf"), expect.stringContaining("bear"), expect.stringContaining("dog"),
      expect.stringContaining("aya"), expect.stringContaining("wolf"), expect.stringContaining("aya"),
    ]);
    await wrapper.find('[data-node="g_wolf"]').trigger("click");
    expect(wrapper.findAll(".equip button[data-slot]").map((button) => button.text())).toEqual([expect.stringMatching(/^Equip A1/)]);
    await wrapper.find('[data-node="g_aya"]').trigger("click");
    expect(wrapper.findAll(".equip button[data-slot]").map((button) => button.text())).toEqual([expect.stringMatching(/^Equip P2/)]);
    await wrapper.find('.equip button[data-slot="p2"]').trigger("click");
    await flushPromises();
    expect(client.saveLoadout).toHaveBeenCalledWith("guardian", { a1: "g_wolf", a2: null, a3: null, a4: null, p1: null, p2: "g_aya" });
  });

  it("displays the server's loadout error", async () => {
    client.saveLoadout.mockRejectedValue(new Error("'g_b' cannot go in slot 'a1'"));
    const wrapper = await mountTab();
    await wrapper.find('[data-node="g_b"]').trigger("click");
    await wrapper.find('.equip button[data-slot="a1"]').trigger("click");
    await flushPromises();
    expect(wrapper.find(".tree-tab .em-notice").text()).toContain("'g_b' cannot go in slot 'a1'");
  });
});
