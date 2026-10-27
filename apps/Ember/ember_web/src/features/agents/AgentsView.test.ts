import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountAgentsClient, agentsClient, type AgentListing } from "./api/AgentsClient";
import AgentsView from "./AgentsView.vue";

vi.mock("./api/AgentsClient", () => ({ agentsClient: { list: vi.fn() }, accountAgentsClient: { get: vi.fn(), set: vi.fn() } }));

const list = vi.mocked(agentsClient.list);
const mine = vi.mocked(accountAgentsClient.get);
const setUse = vi.mocked(accountAgentsClient.set);

const agent = (id: string, extra: Partial<AgentListing> = {}): AgentListing => ({
  id,
  label: id.toUpperCase(),
  entry: false,
  orchestrator: false,
  focus: `${id} does things.`,
  status: "running",
  provider: null,
  gateway: null,
  model: null,
  tiers: [],
  ...extra,
});

const AGENTS = [
  agent("ember", { entry: true, orchestrator: true, provider: "anthropic", gateway: "openrouter", model: "claude-sonnet-5-5" }),
  agent("reviewer"),
  agent("pdf", { status: "offline" }),
  agent("old", { status: "disabled", focus: "" }),
];

type Wrapper = ReturnType<typeof mount>;

const chip = (wrapper: Wrapper, text: string) => wrapper.findAll("button").find((b) => b.text() === text)!;

async function mountView() {
  const wrapper = mount(AgentsView);
  await flushPromises();
  return wrapper;
}

const cards = (wrapper: Wrapper) => wrapper.findAll(".agent-card");

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  list.mockResolvedValue(AGENTS);
  mine.mockResolvedValue({ disabled: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("AgentsView", () => {
  it("shows the internal Router even while disabled without offering it as a chat target", async () => {
    list.mockResolvedValue([agent("router", { internal_role: "router", status: "disabled",
      decision: { choose_agent: true, choose_tier: true, english: true, typed: true, fallback: true } })]);
    const wrapper = await mountView();
    expect(cards(wrapper)[0].text()).toContain("Internal / Router");
    expect(cards(wrapper)[0].text()).toContain("Jev fallback");
    expect(cards(wrapper)[0].text()).toContain("Disabled");
    expect(cards(wrapper)[0].text()).not.toContain("Start chat");
    wrapper.unmount();
  });
  it("shows a card per agent with its name, id, focus and a status word", async () => {
    const wrapper = await mountView();

    const found = cards(wrapper);
    expect(found).toHaveLength(4);
    expect(chip(wrapper, "Refresh").exists()).toBe(true);
    expect(found[1].find("h3").text()).toBe("REVIEWER");
    expect(found[1].find(".agent-id").text()).toBe("reviewer");
    expect(found[1].find(".focus").text()).toBe("reviewer does things.");
    expect(found.map((c) => c.find(".status").text())).toEqual(["● Running", "● Running", "○ Offline", "– Disabled"]);
  });

  it("marks the entry agent and the orchestrator, and nobody else", async () => {
    const wrapper = await mountView();

    const found = cards(wrapper);
    expect(found[0].classes()).toContain("entry");
    expect(found[0].findAll(".tag").map((t) => t.text())).toEqual(["Entry", "Orchestrator"]);
    expect(found[1].classes()).not.toContain("entry");
    expect(found[1].find(".tags").exists()).toBe(false);
  });

  it("says so when an agent has no description", async () => {
    const wrapper = await mountView();

    expect(cards(wrapper)[3].find(".focus").text()).toBe("No description.");
  });

  it("shows provider, gateway and model, and hides the ones an agent does not set", async () => {
    list.mockResolvedValue([
      AGENTS[0],
      agent("partial", { provider: "openai" }),
      agent("bare"),
    ]);
    const wrapper = await mountView();

    const found = cards(wrapper);
    expect(found[0].findAll("dt").map((t) => t.text())).toEqual(["Provider", "Gateway", "Model"]);
    expect(found[0].findAll("dd").map((t) => t.text())).toEqual(["anthropic", "openrouter", "claude-sonnet-5-5"]);
    expect(found[0].find('.llm').element.closest('button')).toBeNull();
    expect(found[0].find('.status').element.closest('button')).toBeNull();
    expect(found[1].findAll("dt").map((t) => t.text())).toEqual(["Provider"]);
    expect(found[2].find(".llm").exists()).toBe(false);
  });

  it("lists each tier with its model, keeps what the tier is for in a title, and hides an empty list", async () => {
    list.mockResolvedValue([
      agent("ember", {
        tiers: [
          { tier: "light", id: "haiku", use_for: "quick lookups" },
          { tier: "heavy", id: "opus", use_for: "hard reasoning" },
        ],
      }),
      agent("bare"),
    ]);
    const wrapper = await mountView();

    const found = cards(wrapper);
    const items = found[0].findAll(".tiers li");
    expect(items.map((li) => li.findAll("span").map((span) => span.text()))).toEqual([
      ["light", "haiku"],
      ["heavy", "opus"],
    ]);
    expect(items[0].find(".tier-model").attributes("title")).toBe("quick lookups");
    expect(found[0].findAll("dt")).toHaveLength(0);
    expect(found[1].find(".tiers").exists()).toBe(false);
  });

  it("summarises the statuses and leaves out the empty ones", async () => {
    const wrapper = await mountView();
    expect(wrapper.find(".summary").text()).toBe("2 running · 1 offline · 1 disabled");

    list.mockResolvedValue([agent("ember", { entry: true })]);
    await chip(wrapper, "Refresh").trigger("click");
    await flushPromises();

    expect(wrapper.find(".summary").text()).toBe("1 running");
  });

  it("says when there are no agents", async () => {
    list.mockResolvedValue([]);

    const wrapper = await mountView();

    expect(wrapper.text()).toContain("No agents are running or defined.");
    expect(cards(wrapper)).toHaveLength(0);
  });

  it("shows the error and keeps the cards it already had when a refresh fails", async () => {
    const wrapper = await mountView();
    list.mockRejectedValue(new Error("boom"));

    await chip(wrapper, "Refresh").trigger("click");
    await flushPromises();

    expect(wrapper.find(".error").text()).toContain("boom");
    expect(cards(wrapper)).toHaveLength(4);
  });

  it("refreshes every 15 seconds and stops when the page closes", async () => {
    const wrapper = await mountView();
    expect(list).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(15_000);
    expect(list).toHaveBeenCalledTimes(2);

    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("offers the switch on specialists only and keeps it pending until the server answers", async () => {
    mine.mockResolvedValue({ disabled: ["pdf"] });
    let answer!: (value: { disabled: string[] }) => void;
    setUse.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    const wrapper = await mountView();

    const boxes = wrapper.findAll<HTMLInputElement>(".agent-card input[role=switch]");
    expect(boxes).toHaveLength(3); // not the entry agent
    const reviewer = wrapper.findAll(".agent-card").find((c) => c.text().includes("REVIEWER"))!;
    expect(reviewer.find<HTMLInputElement>("input").element.checked).toBe(true);
    const pdf = wrapper.findAll(".agent-card").find((c) => c.text().includes("PDF"))!;
    expect(pdf.find<HTMLInputElement>("input").element.checked).toBe(false);

    await reviewer.find("input").setValue(false);
    expect(setUse).toHaveBeenCalledWith("reviewer", false);
    expect(reviewer.attributes("aria-busy")).toBe("true");
    expect(reviewer.find<HTMLInputElement>("input").element.disabled).toBe(true);
    expect(reviewer.find<HTMLInputElement>("input").element.checked).toBe(true);

    answer({ disabled: ["pdf", "reviewer"] });
    await flushPromises();
    expect(reviewer.find<HTMLInputElement>("input").element.checked).toBe(false);
    expect(reviewer.attributes("aria-busy")).toBe("false");
    wrapper.unmount();
  });

  it("groups entry and Router at the front, keeping an entry orchestrator in only one group", async () => {
    list.mockResolvedValue([...AGENTS, agent("router", { internal_role: "router" }), agent("coordinator", { orchestrator: true })]);
    const wrapper = await mountView();
    const groups = wrapper.findAll(".agent-group");
    expect(groups).toHaveLength(2);
    expect(groups[0].findAll(".agent-id").map(id => id.text())).toEqual(["ember", "router"]);
    expect(groups[1].findAll(".agent-id").map(id => id.text())).toEqual(["coordinator", "reviewer", "pdf", "old"]);
    expect(cards(wrapper)).toHaveLength(6);
    wrapper.unmount();
  });

  it("combines status and model search, clears filters and preserves choices through refresh", async () => {
    list.mockResolvedValue([...AGENTS, agent("research", { status: "offline", tiers: [{ tier: "deep", id: "opus", use_for: "research" }] })]);
    const wrapper = await mountView();
    await chip(wrapper, "Offline").trigger("click");
    await wrapper.find('input[type="search"]').setValue("opus");
    expect(cards(wrapper).map(card => card.find('.agent-id').text())).toEqual(["research"]);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(cards(wrapper)).toHaveLength(1);
    expect(wrapper.find('input[type="search"]').element).toHaveProperty('value', 'opus');
    await wrapper.find('input[type="search"]').setValue("missing");
    expect(wrapper.text()).toContain("No matching agents");
    await chip(wrapper, "Clear filters").trigger("click");
    expect(cards(wrapper)).toHaveLength(5);
    wrapper.unmount();
  });

  it("restores the confirmed switch value on failure and retains the roster", async () => {
    setUse.mockRejectedValue(new Error("Could not save preference"));
    const wrapper = await mountView();
    const reviewer = cards(wrapper)[1];
    await reviewer.find("input").setValue(false);
    await flushPromises();
    expect(reviewer.find<HTMLInputElement>("input").element.checked).toBe(true);
    expect(wrapper.text()).toContain("Could not save preference");
    expect(cards(wrapper)).toHaveLength(4);
    wrapper.unmount();
  });

  it("offers retry after an initial failure", async () => {
    list.mockRejectedValueOnce(new Error("offline"));
    const wrapper = await mountView();
    expect(wrapper.find('[role="alert"]').text()).toContain("offline");
    await chip(wrapper, "Try again").trigger("click");
    await flushPromises();
    expect(cards(wrapper)).toHaveLength(4);
    wrapper.unmount();
  });

  it("keeps the full description outside filters that remove its card", async () => {
    const realShow = HTMLDialogElement.prototype.showModal;
    HTMLDialogElement.prototype.showModal = vi.fn();
    const wrapper = await mountView();
    await cards(wrapper)[1].find('button').trigger('click');
    expect(wrapper.find('dialog').attributes('aria-label')).toBe('REVIEWER');
    await chip(wrapper, 'Offline').trigger('click');
    expect(cards(wrapper)).toHaveLength(1);
    expect(wrapper.find('dialog').text()).toContain('reviewer does things.');
    expect(wrapper.find('dialog').element.closest('.agent-group')).toBeNull();
    wrapper.unmount();
    HTMLDialogElement.prototype.showModal = realShow;
  });

  it("does not let an older refresh overwrite a newly confirmed preference", async () => {
    const wrapper = await mountView();
    let finishRead!: (value: { disabled: string[] }) => void;
    mine.mockReturnValueOnce(new Promise(resolve => { finishRead = resolve; }));
    await chip(wrapper, 'Refresh').trigger('click');
    setUse.mockResolvedValue({ disabled: ['reviewer'] });
    await cards(wrapper)[1].find('input').setValue(false);
    await flushPromises();
    finishRead({ disabled: [] });
    await flushPromises();
    expect(cards(wrapper)[1].find<HTMLInputElement>('input').element.checked).toBe(false);
    wrapper.unmount();
  });
});
