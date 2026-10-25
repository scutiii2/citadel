// apps/Ember/ember_web/src/features/settings/components/ResponseLimits.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import { tuningClient, type AccountLimits } from "../../../api/navigation/TuningClient";
import ResponseLimits from "./ResponseLimits.vue";

vi.mock("../../../api/navigation/TuningClient", () => ({ tuningClient: { get: vi.fn(), save: vi.fn(), reset: vi.fn() } }));

const body = (limits: Partial<AccountLimits["limits"]> = {}): AccountLimits => ({
  limits: { max_output_tokens: null, max_tool_rounds: null, ...limits },
  ceiling: { max_output_tokens: 2048, max_tool_rounds: 15 },
});

beforeEach(() => vi.clearAllMocks());

async function show(value: AccountLimits) {
  vi.mocked(tuningClient.get).mockResolvedValue(value);
  const wrapper = mount(ResponseLimits);
  await flushPromises();
  return wrapper;
}

it("shows the admin value as the maximum and an empty box when unset", async () => {
  const wrapper = await show(body());
  const rounds = wrapper.get('[data-field="max_tool_rounds"]');
  expect((rounds.element as HTMLInputElement).value).toBe("");
  expect(rounds.attributes("max")).toBe("15");
  expect(wrapper.text()).toContain("15");
});

it("saves both values, sending null for an empty box", async () => {
  const wrapper = await show(body());
  vi.mocked(tuningClient.save).mockResolvedValue(body({ max_tool_rounds: 4 }));
  await wrapper.get('[data-field="max_tool_rounds"]').setValue("4");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(tuningClient.save).toHaveBeenCalledWith({ max_output_tokens: null, max_tool_rounds: 4 });
});

it("shows the refusal when a value is above the admin's", async () => {
  const wrapper = await show(body());
  vi.mocked(tuningClient.save).mockRejectedValue(new Error("max_tool_rounds cannot be above 15"));
  await wrapper.get('[data-field="max_tool_rounds"]').setValue("40");
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("cannot be above 15");
});

it("clears both limits", async () => {
  const wrapper = await show(body({ max_tool_rounds: 4 }));
  vi.mocked(tuningClient.reset).mockResolvedValue(undefined);
  await wrapper.get('[data-test="clear"]').trigger("click");
  await flushPromises();
  expect(tuningClient.reset).toHaveBeenCalled();
  expect((wrapper.get('[data-field="max_tool_rounds"]').element as HTMLInputElement).value).toBe("");
});

it("keeps Save off until a value changed", async () => {
  const wrapper = await show(body({ max_tool_rounds: 4 }));
  expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
});
