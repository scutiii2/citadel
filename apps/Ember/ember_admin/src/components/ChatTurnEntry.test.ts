import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { LogEntry } from "../api/LogsClient";
import ChatTurnEntry from "./ChatTurnEntry.vue";

const DETAILS = JSON.stringify({
  response: "5",
  agents: [
    { agent_id: "claude-agent", agent_label: "Ember", model: "claude-test", total_tokens: 100, input_tokens: 70, output_tokens: 30, model_tier: "heavy", tools: ["notes"] },
    { agent_id: "calc", delegated_by: "claude-agent", model: "gpt-x", total_tokens: 25, started_at: "2026-10-04T09:12:04.000Z", finished_at: "2026-10-04T09:12:05.250Z", tools: [] },
  ],
});
const PROMPTS = JSON.stringify([
  { messages: [{ role: "user", content: "earlier" }, { role: "user", content: "add 2 and 3" }], truncated: true },
  { messages: [{ role: "user", content: "2 + 3" }], truncated: false },
]);

function entry(over: Partial<LogEntry> = {}): LogEntry {
  return { id: 1, kind: "chat_trace", account_id: 1, source: "chat.turn", message: "q", details: DETAILS, prompts: PROMPTS, created_at: "2026-10-04T09:12:00", ...over };
}

describe("ChatTurnEntry", () => {
  it("normal view lists every agent with its model and tokens, and keeps the raw details", () => {
    const wrapper = mount(ChatTurnEntry, { props: { entry: entry(), advanced: false } });
    const items = wrapper.findAll(".agents li").map((li) => li.findAll("span, code").map((part) => part.text()));
    expect(items).toEqual([["Ember", "claude-test", "100 tokens"], ["calc", "gpt-x", "25 tokens"]]);
    expect(wrapper.find("details pre").text()).toBe(DETAILS);
    expect(wrapper.text()).not.toContain("add 2 and 3");
  });

  it("advanced view shows each agent's delegation, timing, tools and prompt", () => {
    const wrapper = mount(ChatTurnEntry, { props: { entry: entry(), advanced: true } });
    const [first, second] = wrapper.findAll(".run");
    expect(first!.text()).toContain("answered the question");
    expect(first!.text()).toContain("tier heavy");
    expect(first!.text()).toContain("Tools: notes");
    expect(first!.text()).toContain("Prompt (2 messages) · shortened");
    expect(first!.text()).toContain("add 2 and 3");
    expect(second!.text()).toContain("delegated by claude-agent");
    expect(second!.text()).toContain("1.3s");
    expect(second!.text()).toContain("Prompt (1 message)");
    expect(second!.text()).not.toContain("shortened");
    expect(wrapper.text()).toContain("The system prompt is not recorded.");
  });

  it("says so when an entry has no agents or no prompt", () => {
    const old = mount(ChatTurnEntry, { props: { entry: entry({ details: '{"response":"x"}', prompts: null }), advanced: true } });
    expect(old.text()).toContain("logged before agents were recorded");

    const hidden = mount(ChatTurnEntry, { props: { entry: entry({ prompts: null }), advanced: true } });
    expect(hidden.findAll(".prompt")).toHaveLength(0);
    expect(hidden.text()).toContain("No prompt recorded.");
  });
});
