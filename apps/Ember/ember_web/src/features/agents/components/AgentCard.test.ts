import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { AgentListing } from "../api/AgentsClient";
import AgentCard from "./AgentCard.vue";

const agent: AgentListing = {
  id: "code-architect", label: "Code architect", entry: false, orchestrator: false,
  focus: "Plans implementation.", status: "disabled", provider: null, gateway: null,
  model: null, tiers: [], architect: { kind: "code", workers: ["code-writer", "reviewer"] },
};

describe("AgentCard", () => {
  it("shows the architect badge, workers and plan-mode footer without a toggle", () => {
    const wrapper = mount(AgentCard, { props: { agent, off: true } });
    expect(wrapper.find(".call-chip").text()).toBe("Architect · code");
    expect(wrapper.text()).toContain("Builds with: code-writer, reviewer");
    expect(wrapper.find('[role="switch"]').exists()).toBe(false);
    expect(wrapper.find(".managed").text()).toBe("Used by the orchestrator in plan mode");
    expect(wrapper.text()).not.toContain("Specialist");
    expect(wrapper.text()).toContain("Disabled");
  });

  it("omits the workers line when there are no workers", () => {
    const wrapper = mount(AgentCard, { props: { agent: { ...agent, architect: { kind: "code", workers: [] } } } });
    expect(wrapper.text()).not.toContain("Builds with:");
  });

  it("preserves specialist switches and managed-agent footers", () => {
    const specialist = { ...agent, architect: null };
    const wrapper = mount(AgentCard, { props: { agent: specialist } });
    expect(wrapper.find(".call-chip").text()).toBe("Specialist");
    expect(wrapper.find('[role="switch"]').exists()).toBe(true);
    for (const [extra, footer] of [
      [{ entry: true }, "Every new chat starts here"],
      [{ orchestrator: true }, "Available to the entry agent"],
      [{ internal_role: "router" as const }, "Internal · does not answer chats"],
    ] as const) {
      const managed = mount(AgentCard, { props: { agent: { ...specialist, ...extra } } });
      expect(managed.find('[role="switch"]').exists()).toBe(false);
      expect(managed.find(".managed").text()).toBe(footer);
    }
  });
});
