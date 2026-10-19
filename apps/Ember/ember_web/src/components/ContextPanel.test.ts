import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ContextPanel from "./ContextPanel.vue";

const PARTS = [
  { id: "system_prompt", label: "System prompt", tokens: 9_000 },
  { id: "mcp_tools", label: "MCP tools", tokens: 17_700 },
  { id: "messages", label: "Messages", tokens: 172_100 },
];

function mountPanel(props: Partial<InstanceType<typeof ContextPanel>["$props"]> = {}) {
  return mount(ContextPanel, { props: { tokens: 198_800, window: 1_000_000, parts: PARTS, ...props } });
}

const row = (w: ReturnType<typeof mountPanel>, id: string) => w.get(`[data-part="${id}"]`);

describe("ContextPanel", () => {
  it("lists each agent call's prompt cost without adding it to the answering agent's window", () => {
    const w = mountPanel({ agentUsage: [
      { agent: "ember", agent_label: "Ember", total_tokens: 100, context_breakdown: PARTS, context_breakdown_exact: true },
      { agent: "calc", agent_label: "Calculator", total_tokens: 25,
        context_breakdown: [{ id: "messages", label: "Messages", tokens: 20 }], context_breakdown_exact: false },
      { agent: "calc", agent_label: "Calculator", total_tokens: 35,
        context_breakdown: [{ id: "system_prompt", label: "System prompt", tokens: 30 }] },
      { agent: "old", total_tokens: 10 },
    ] });
    const agents = w.findAll("[data-test=agent-context]");
    expect(agents).toHaveLength(4);
    expect(agents[0]!.text()).toContain("Ember");
    expect(agents[0]!.text()).toContain("Exact");
    expect(agents[1]!.text()).toContain("Calculator");
    expect(agents[1]!.text()).toContain("Estimated");
    expect(agents[1]!.text()).toContain("20");
    expect(agents[2]!.text()).toContain("System prompt");
    expect(agents[3]!.text()).toContain("Breakdown unavailable");
    expect(w.get("[data-test=agent-contexts]").text()).toContain("Prompt cost per agent");
    expect(w.get("[data-test=agent-contexts]").text()).not.toContain("Free space");
    expect(w.get(".summary").text()).toContain("20% used");
  });

  it("keeps the original view for answers without per-agent usage", () => {
    expect(mountPanel().find("[data-test=agent-contexts]").exists()).toBe(false);
  });
  it("says how much of the window is used", () => {
    const w = mountPanel();

    expect(w.get(".summary").text()).toContain("20% used");
    expect(w.get(".summary").text()).toContain("199k");
    expect(w.get(".summary").text()).toContain("1M");
  });

  it("lists every part with its tokens and its share of the window, then the free space", () => {
    const w = mountPanel();

    expect(w.findAll("li").map((li) => li.attributes("data-part"))).toEqual([
      "system_prompt",
      "mcp_tools",
      "messages",
      "free",
    ]);
    expect(row(w, "messages").text()).toContain("Messages");
    expect(row(w, "messages").text()).toContain("172k");
    expect(row(w, "messages").text()).toContain("17.2%");
    expect(row(w, "free").text()).toContain("Free space");
    expect(row(w, "free").text()).toContain("80.1%");
  });

  it("gives every kind of part its own colour, in the bar and in its row", () => {
    const parts = ["system_prompt", "agents", "builtin_tools", "mcp_tools", "messages"].map((id) => ({ id, label: id, tokens: 100 }));
    const w = mountPanel({ parts });

    const swatches = w.findAll("li:not([data-part=free]) .swatch").map((s) => s.attributes("style"));
    expect(new Set(swatches).size).toBe(5);
    expect(swatches[0]).toContain("--part-system_prompt");
    expect(w.findAll(".bar i").map((i) => i.attributes("style"))).toEqual(
      expect.arrayContaining([expect.stringContaining("--part-messages")]),
    );
  });

  it("falls back to a neutral colour for a part it does not know", () => {
    const w = mountPanel({ parts: [{ id: "something_new", label: "New", tokens: 100 }] });

    expect(w.get("[data-part=something_new] .swatch").attributes("style")).toContain("var(--part-other)");
  });

  it("draws one bar segment per part, not for the free space", () => {
    const w = mountPanel();

    const segments = w.findAll(".bar i");
    expect(segments).toHaveLength(3);
    expect(segments[2]!.attributes("style")).toContain("width: 17.21%");
  });

  it("says whether the parts were estimated or counted by the provider", () => {
    expect(mountPanel().get("[data-test=context-note]").text()).toContain("Estimated from the prompt text");
    expect(mountPanel({ exact: true }).get("[data-test=context-note]").text()).toContain("Counted by the model provider");
  });

  it("has no accuracy switch unless it is given the setting", () => {
    expect(mountPanel().find("[data-test=context-accuracy]").exists()).toBe(false);
  });

  it("shows the accuracy and emits the one chosen", async () => {
    const w = mountPanel({ accuracy: "estimate" });
    const button = (label: string) => w.findAll("[data-test=context-accuracy] button").find((b) => b.text() === label)!;

    expect(button("Estimate").attributes("aria-pressed") ?? button("Estimate").classes().join(" ")).toBeTruthy();
    await button("Exact").trigger("click");

    expect(w.emitted("update:accuracy")).toEqual([["exact"]]);
    expect(w.get("[data-test=context-accuracy]").text()).toContain("Applies from your next question");
  });

  it("shows a tiny part as under 0.1%", () => {
    const w = mountPanel({ tokens: 10_001, parts: [{ id: "agents", label: "Delegable agents", tokens: 1 }] });

    expect(row(w, "agents").text()).toContain("<0.1%");
  });

  it("has no free space left when the context is full", () => {
    const w = mountPanel({ tokens: 1_000_000, window: 1_000_000 });

    expect(row(w, "free").text()).toContain("0.0%");
    expect(w.get(".summary").text()).toContain("100% used");
  });
});
