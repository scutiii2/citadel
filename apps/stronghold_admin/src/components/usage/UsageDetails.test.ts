import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { MyUsage, UsageRecordRow } from "../../api/UsageClient";
import UsageDetails from "./UsageDetails.vue";

const usage: MyUsage = {
  six_hour: { used: 0, limit: 0, reset_at: null }, weekly: { used: 0, limit: 0, reset_at: null },
  report: { days: 30, since: "2026-10-01", total_tokens: 0, input_tokens: 0, output_tokens: 0,
    summary_tokens: 0, turns: 0, chats: 0, by_agent: [], daily: [], hourly: Array(24).fill(0), group_by: "agent", groups: [] },
};

const show = (records: UsageRecordRow[] = []) =>
  mount(UsageDetails, { props: { username: "alice", usage, year: null, records, recordsFailed: false, yearFailed: false, loading: false, groupBy: "agent" } });

function row(extra: Partial<UsageRecordRow> = {}): UsageRecordRow {
  return {
    id: 1, turn_id: "t", kind: "chat", chat_id: "c", agent: "calc", agent_id: "calc", provider_id: "openai", gateway: "azure",
    model: "gpt-x", input_tokens: 20, output_tokens: 5, total_tokens: 25, started_at: "2026-10-04T09:12:04",
    finished_at: "2026-10-04T09:12:05", delegated_by: "main", created_at: "2026-10-04T09:12:06", ...extra,
  };
}

it("labels the target and emits grouping changes without fetching personal data", async () => {
  const w = show();
  expect(w.attributes("aria-label")).toBe("Usage for alice");
  expect(w.text()).toContain("No limit");
  expect(w.text()).toContain("No usage in this period");
  await w.findAll("button").find(b => b.text() === "Provider")!.trigger("click");
  expect(w.emitted("group")).toEqual([["provider"]]);
  w.unmount();
});

describe("recent calls grouped by response", () => {
  const delegated = (turn: string) => [
    row({ id: 11, turn_id: turn, agent: "helper", agent_id: "helper", delegated_by: "main", started_at: "2026-10-04T09:12:05", total_tokens: 30 }),
    row({ id: 10, turn_id: turn, agent: "main", agent_id: "main", delegated_by: null, started_at: "2026-10-04T09:12:01", total_tokens: 70 }),
    row({ id: 12, turn_id: turn, agent: "calc", agent_id: "calc", delegated_by: "main", started_at: "2026-10-04T09:12:08", total_tokens: 5 }),
  ];

  it("shows one collapsed header for the calls that share a turn, with their total", () => {
    const w = show(delegated("t1"));

    expect(w.findAll(".calls > li")).toHaveLength(1);
    const head = w.get(".turn-head");
    expect(head.text()).toContain("main");
    expect(head.text()).toContain("3 calls");
    expect(head.get(".turn-total").text()).toBe("105");
    expect(head.attributes("aria-expanded")).toBe("false");
    expect(w.find(".turn-calls").exists()).toBe(false);
    w.unmount();
  });

  it("opens a header to its calls, the orchestrator first and the rest in the order they ran", async () => {
    const w = show(delegated("t1"));

    await w.get(".turn-head").trigger("click");

    expect(w.get(".turn-head").attributes("aria-expanded")).toBe("true");
    expect(w.findAll(".turn-calls .call-agent").map(a => a.text())).toEqual(["main", "helper", "calc"]);
    await w.get(".turn-head").trigger("click");
    expect(w.find(".turn-calls").exists()).toBe(false);
    w.unmount();
  });

  it("keeps separate turns apart, and shows a lone call as a plain row with no header", () => {
    const w = show([...delegated("t1"), row({ id: 20, turn_id: "t2", agent_id: "solo" })]);

    const items = w.findAll(".calls > li");
    expect(items).toHaveLength(2);
    expect(items[0]!.classes()).toContain("turn");
    expect(items[1]!.classes()).toContain("call");
    expect(items[1]!.text()).toContain("solo");
    expect(w.findAll(".turn-head")).toHaveLength(1);
    w.unmount();
  });
});
