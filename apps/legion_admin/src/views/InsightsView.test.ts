import { flushPromises, mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import { tuningClient } from "../api/TuningClient";
import InsightsView from "./InsightsView.vue";

const data = {
  days: 7,
  history: {
    "2026-11-23": { "router.turns": 4, "router.agent_picked": 3, "router.tier.light": 2, "confidential.marked.check": 1, "tokens.user.ann@example.com": 900 },
    "2026-11-24": { "router.turns": 6, "router.agent_picked": 3, "router.agent_uncertain": 3, "confidential.marked.recall": 2, "confidential.failed_closed": 1,
      "batch.parallel_groups": 5, "tokens.user.ann@example.com": 1200, "tokens.user.bob@example.com": 300, "tokens.agent.ember": 1500 },
  },
  budgets: { turn_tokens: 100000, turn_seconds: 300, daily_tokens_per_user: 2000, daily_tokens_per_agent: 0 },
};

it("sums the counters over the days and lists today's tokens, biggest first", async () => {
  const insights = vi.spyOn(tuningClient, "insights").mockResolvedValue(data);
  const wrapper = mount(InsightsView, { global: { stubs: { teleport: true } } });
  await flushPromises();
  expect(insights).toHaveBeenCalledWith(7);
  const text = wrapper.text();
  expect(text).toContain("Picked share: 60%");
  expect(text).toContain("Turns marked confidential3");
  expect(text).toContain("Failed closed1");
  expect(text).toContain("Daily budget per user: 2,000. Per agent: no limit.");
  const users = wrapper.get('[data-test="users"]').findAll("tbody tr").map((row) => row.text());
  expect(users).toEqual(["ann@example.com1,200", "bob@example.com300"]);
  expect(wrapper.get('[data-test="agents"]').text()).toContain("ember1,500");
  await wrapper.get('[data-test="days"]').setValue(14);
  expect(insights).toHaveBeenLastCalledWith(14);
});

it("shows the error and a Retry when the counters cannot be read", async () => {
  vi.spyOn(tuningClient, "insights").mockRejectedValue(new Error("down"));
  const wrapper = mount(InsightsView);
  await flushPromises();
  expect(wrapper.text()).toContain("down");
  expect(wrapper.find("button.small").text()).toBe("Retry");
});
