import { describe, expect, it } from "vitest";
import { agentRuns, durationSeconds, parsePrompts, parseTraceAgents } from "./chatTrace";

const DETAILS = JSON.stringify({
  chat_id: "c1",
  agent: "claude-agent",
  agents: [
    { agent_id: "claude-agent", agent_label: "Ember", model: "m1", total_tokens: 100, input_tokens: 70, output_tokens: 30, tools: ["notes"] },
    { agent_id: "calc", delegated_by: "claude-agent", provider_id: "openai", started_at: "2026-10-04T09:12:04.000Z", finished_at: "2026-10-04T09:12:05.250Z", tools: [] },
  ],
});

describe("parseTraceAgents", () => {
  it("lists the agents of a chat turn", () => {
    expect(parseTraceAgents(DETAILS).map((a) => a.agent_id)).toEqual(["claude-agent", "calc"]);
  });

  it("is empty for older entries, other kinds and broken text", () => {
    expect(parseTraceAgents(JSON.stringify({ chat_id: "c1" }))).toEqual([]);
    expect(parseTraceAgents("not json")).toEqual([]);
    expect(parseTraceAgents(null)).toEqual([]);
    expect(parseTraceAgents(JSON.stringify({ agents: [1, null, { model: "no id" }] }))).toEqual([]);
  });
});

describe("parsePrompts", () => {
  it("reads one prompt per agent, in order", () => {
    const text = JSON.stringify([{ messages: [{ role: "user", content: "hi" }], truncated: true }, { messages: [], truncated: false }]);
    expect(parsePrompts(text)).toEqual([{ messages: [{ role: "user", content: "hi" }], truncated: true }, { messages: [], truncated: false }]);
  });

  it("is empty when absent or broken", () => {
    expect(parsePrompts(null)).toEqual([]);
    expect(parsePrompts("{")).toEqual([]);
    expect(parsePrompts('{"a":1}')).toEqual([]);
  });
});

describe("durationSeconds", () => {
  it("is the time between two ISO times", () => {
    expect(durationSeconds("2026-10-04T09:12:04.000Z", "2026-10-04T09:12:05.250Z")).toBe(1.3);
  });

  it("is null when a time is missing or unreadable", () => {
    expect(durationSeconds(undefined, "2026-10-04T09:12:05Z")).toBeNull();
    expect(durationSeconds("x", "y")).toBeNull();
  });
});

describe("agentRuns", () => {
  it("pairs each agent with its prompt by position", () => {
    const prompts = [{ messages: [{ role: "user", content: "q" }], truncated: false }];
    const runs = agentRuns(DETAILS, JSON.stringify(prompts));
    expect(runs).toHaveLength(2);
    expect(runs[0]!.prompt?.messages[0]?.content).toBe("q");
    expect(runs[1]!.prompt).toBeNull();
    expect(runs[1]!.seconds).toBe(1.3);
  });
});
