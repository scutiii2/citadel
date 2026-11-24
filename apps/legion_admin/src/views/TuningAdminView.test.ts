// apps/Ember/ember_admin/src/views/TuningAdminView.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { tuningClient, type TuningView } from "../api/TuningClient";
import TuningAdminView from "./TuningAdminView.vue";

vi.mock("../api/TuningClient", () => ({ tuningClient: { get: vi.fn(), save: vi.fn() } }));

const view = (overrides: TuningView["overrides"] = {}): TuningView => {
  const defaults = {
    token_limits: { default: { max_output_tokens: 2048, max_context_tokens: 100000, max_tool_rounds: 15 } },
    gateway_failover: { quota_cooldown_seconds: 3600, auth_cooldown_seconds: 3600, unavailable_cooldown_seconds: 30 },
    tool_batch: { parallel: true, max_parallel: 8, batch_tool: true, max_steps: 10, max_result_chars: 20000, max_total_chars: 60000 },
    classifier: {
      timeout_seconds: 3, max_input_chars: 16000,
      auto_tier: { strategy: "both", min_confidence: 80 },
      auto_route: { strategy: "both", min_confidence: 80 },
    },
  };
  return { defaults, overrides, effective: defaults };
};

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
});
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

it("selects a decision strategy and saves it", async () => {
  const wrapper = await show(view());
  vi.mocked(tuningClient.save).mockResolvedValue(view({ "classifier.auto_tier.strategy": "laya-only" }));
  await wrapper.get('[data-path="classifier.auto_tier.strategy"]').setValue("laya-only");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(tuningClient.save).toHaveBeenCalledWith({ "classifier.auto_tier.strategy": "laya-only" });
});

it("shows the refusal and keeps the draft", async () => {
  const wrapper = await show(view());
  vi.mocked(tuningClient.save).mockRejectedValue(new Error("Tuning service unavailable"));
  const rounds = wrapper.get('[data-path="token_limits.default.max_tool_rounds"]');
  await rounds.setValue("40");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("Tuning service unavailable");
  expect((rounds.element as HTMLInputElement).value).toBe("40");
});

it("reserves two slots and shows the named Cancel × before Save only when dirty", async () => {
  const wrapper = await show(view());
  const slots = wrapper.findAll(".draft-actions .action-slot");
  expect(slots).toHaveLength(2);
  expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
  expect(wrapper.find('[data-test="cancel"]').exists()).toBe(false);
  await wrapper.get('[data-path="token_limits.default.max_tool_rounds"]').setValue("4");
  expect(wrapper.get('[data-test="cancel"]').attributes("aria-label")).toBe("Cancel tuning changes");
  expect(wrapper.get('[data-test="cancel"]').element.parentElement).toBe(slots[0]!.element);
  expect(wrapper.get('[data-test="save"]').element.parentElement).toBe(slots[1]!.element);
});


it("protects an unsaved admin draft from page unload until cancelled", async () => {
  const wrapper = await show(view());
  await wrapper.get('[data-path="token_limits.default.max_tool_rounds"]').setValue("4");
  const dirtyEvent = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(dirtyEvent);
  expect(dirtyEvent.defaultPrevented).toBe(true);
  await wrapper.get('[data-test="cancel"]').trigger("click");
  await wrapper.get('dialog[open] button.confirm').trigger("click");
  const cleanEvent = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(cleanEvent);
  expect(cleanEvent.defaultPrevented).toBe(false);
});


it("saves edits hidden by search with visible edits", async () => {
  const wrapper = await show(view());
  const path = "token_limits.default.max_tool_rounds";
  await wrapper.get(`[data-path="${path}"]`).setValue("20");
  await wrapper.get('input[type="search"]').setValue("after an outage");
  expect(wrapper.find(`[data-path="${path}"]`).exists()).toBe(false);
  await wrapper.get('[data-path="gateway_failover.unavailable_cooldown_seconds"]').setValue("14");
  vi.mocked(tuningClient.save).mockResolvedValue(view());
  await wrapper.get('[data-test="save"]').trigger("click");
  expect(tuningClient.save).toHaveBeenCalledWith({ [path]: 20, "gateway_failover.unavailable_cooldown_seconds": 14 });
});

it("reveals a hidden invalid draft and refuses to save it", async () => {
  const wrapper = await show(view());
  const path = "token_limits.default.max_tool_rounds";
  await wrapper.get(`[data-path="${path}"]`).setValue("500");
  await wrapper.get('input[type="search"]').setValue("after an outage");
  await wrapper.get('[data-test="save"]').trigger("click");
  expect(tuningClient.save).not.toHaveBeenCalled();
  expect(wrapper.get(`[data-path="${path}"]`).attributes("aria-invalid")).toBe("true");
  expect(wrapper.get('[role="alert"]').text()).toContain("from 1 to 100");
});


it("keeps the draft after cancelling navigation and discards it after confirmation", async () => {
  vi.mocked(tuningClient.get).mockResolvedValue(view());
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/tuning", component: TuningAdminView },
    { path: "/elsewhere", component: { template: "<div>Elsewhere</div>" } },
  ] });
  await router.push("/tuning");
  const wrapper = mount(RouterView, { global: { plugins: [router] } });
  mounted.push(wrapper);
  await flushPromises();

  await wrapper.get('[data-path="token_limits.default.max_tool_rounds"]').setValue("20");
  const first = router.push("/elsewhere");
  await flushPromises();
  await wrapper.get("dialog[open] .cancel").trigger("click");
  await first;
  expect(router.currentRoute.value.path).toBe("/tuning");
  expect(wrapper.get<HTMLInputElement>('[data-path="token_limits.default.max_tool_rounds"]').element.value).toBe("20");

  const second = router.push("/elsewhere");
  await flushPromises();
  await wrapper.get("dialog[open] .confirm").trigger("click");
  await second;
  expect(router.currentRoute.value.path).toBe("/elsewhere");
  expect(tuningClient.save).not.toHaveBeenCalled();
});


it("edits the tool-call settings, switches included, and shows their defaults as On or Off", async () => {
  const wrapper = await show(view());
  expect(wrapper.text()).toContain("Default: On");
  const steps = wrapper.get('[data-path="tool_batch.max_steps"]');
  expect((steps.element as HTMLInputElement).value).toBe("10");
  await steps.setValue("5");
  await wrapper.get('[data-path="tool_batch.parallel"]').setValue(false);
  vi.mocked(tuningClient.save).mockResolvedValue(view());
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(tuningClient.save).toHaveBeenCalledWith({ "tool_batch.max_steps": 5, "tool_batch.parallel": false });
});
