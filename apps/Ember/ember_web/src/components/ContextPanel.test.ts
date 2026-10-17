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

  it("draws one bar segment per part, not for the free space", () => {
    const w = mountPanel();

    const segments = w.findAll(".bar i");
    expect(segments).toHaveLength(3);
    expect(segments[2]!.attributes("style")).toContain("width: 17.21%");
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
