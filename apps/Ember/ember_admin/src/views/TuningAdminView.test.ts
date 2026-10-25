// apps/Ember/ember_admin/src/views/TuningAdminView.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { tuningClient, type TuningView } from "../api/TuningClient";
import TuningAdminView from "./TuningAdminView.vue";

vi.mock("../api/TuningClient", () => ({ tuningClient: { get: vi.fn(), save: vi.fn() } }));

const view = (overrides: TuningView["overrides"] = {}): TuningView => {
  const defaults = {
    token_limits: { default: { max_output_tokens: 2048, max_context_tokens: 100000, max_tool_rounds: 15 } },
    gateway_failover: { quota_cooldown_seconds: 3600, auth_cooldown_seconds: 3600, unavailable_cooldown_seconds: 30 },
    classifier: {
      timeout_seconds: 3, max_input_chars: 16000, triage_fallback: false, triage_trace: false, triage_window: 4096,
      triage_prune_ratio: 0.25, triage_pair_ratio: 0.5,
      triage_thresholds: { "2": { jev: 0.9 }, "3+": { jev: 0.9 } },
      triage_enabled: { jev: { choice: true, noul: true, score: true } },
    },
  };
  return { defaults, overrides, effective: defaults };
};

beforeEach(() => vi.clearAllMocks());

const mounted: ReturnType<typeof mount>[] = [];
afterEach(() => mounted.splice(0).forEach(w => w.unmount()));

async function show(v: TuningView) {
  vi.mocked(tuningClient.get).mockResolvedValue(v);
  const wrapper = mount(TuningAdminView);
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}

it("shows the effective value and sends only the edited field on Save", async () => {
  const wrapper = await show(view());
  const rounds = wrapper.get('[data-path="token_limits.default.max_tool_rounds"]');
  expect((rounds.element as HTMLInputElement).value).toBe("15");

  await rounds.setValue("20");
  vi.mocked(tuningClient.save).mockResolvedValue(view({ "token_limits.default.max_tool_rounds": 20 }));
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();

  expect(tuningClient.save).toHaveBeenCalledWith({ "token_limits.default.max_tool_rounds": 20 });
});

it("marks a changed field and resets it with null", async () => {
  const wrapper = await show(view({ "gateway_failover.quota_cooldown_seconds": 60 }));
  const row = wrapper.get('[data-row="gateway_failover.quota_cooldown_seconds"]');
  expect(row.attributes("data-changed")).toBe("true");

  vi.mocked(tuningClient.save).mockResolvedValue(view());
  await row.get('[data-test="reset"]').trigger("click");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();

  expect(tuningClient.save).toHaveBeenCalledWith({ "gateway_failover.quota_cooldown_seconds": null });
});

it("toggles a boolean and saves it", async () => {
  const wrapper = await show(view());
  vi.mocked(tuningClient.save).mockResolvedValue(view({ "classifier.triage_trace": true }));
  await wrapper.get('[data-path="classifier.triage_trace"]').setValue(true);
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(tuningClient.save).toHaveBeenCalledWith({ "classifier.triage_trace": true });
});

it("shows the refusal and keeps the draft", async () => {
  const wrapper = await show(view());
  vi.mocked(tuningClient.save).mockRejectedValue(new Error("token_limits.default.max_tool_rounds must be from 1 and up to 100"));
  const rounds = wrapper.get('[data-path="token_limits.default.max_tool_rounds"]');
  await rounds.setValue("500");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("must be from 1 and up to 100");
  expect((rounds.element as HTMLInputElement).value).toBe("500");
});

it("disables Save until something changed", async () => {
  const wrapper = await show(view());
  expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
});


it("protects an unsaved admin draft from page unload until cancelled", async () => {
  const wrapper = await show(view());
  await wrapper.get('[data-path="token_limits.default.max_tool_rounds"]').setValue("4");
  const dirtyEvent = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(dirtyEvent);
  expect(dirtyEvent.defaultPrevented).toBe(true);
  await wrapper.get('[data-test="cancel"]').trigger("click");
  const cleanEvent = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(cleanEvent);
  expect(cleanEvent.defaultPrevented).toBe(false);
});
