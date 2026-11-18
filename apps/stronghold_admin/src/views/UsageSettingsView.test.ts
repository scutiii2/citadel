import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usageSettingsClient, type UsageSettings } from "../api/UsageSettingsClient";
import UsageSettingsView from "./UsageSettingsView.vue";

const SETTINGS: UsageSettings = {
  usage: { six_hour_token_limit: 1000000, weekly_token_limit: 5000000, max_context_tokens_per_chat: 150000, auto_summarize_ratio: 0.6 },
  pricing: { currency: "USD", models: { sonnet: { input: 3, output: 15 } } },
  stored: { usage: false, pricing: true },
};

beforeEach(() => {
  vi.spyOn(usageSettingsClient, "get").mockResolvedValue(SETTINGS);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(UsageSettingsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const save = (wrapper: Awaited<ReturnType<typeof mounted>>) => wrapper.get('[data-test="save"]');

describe("UsageSettingsView", () => {
  it("shows the limits and prices and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((wrapper.get('[data-test="weekly_token_limit"]').element as HTMLInputElement).value).toBe("5000000");
    expect((wrapper.get('[data-test="price-model"]').element as HTMLInputElement).value).toBe("sonnet");
    expect(save(wrapper).attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("sends only the limits when only a limit changed", async () => {
    const send = vi.spyOn(usageSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await wrapper.get('[data-test="weekly_token_limit"]').setValue("0");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(send).toHaveBeenCalledWith({
      usage: { six_hour_token_limit: 1000000, weekly_token_limit: 0, max_context_tokens_per_chat: 150000, auto_summarize_ratio: 0.6 },
    });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next question");
    wrapper.unmount();
  });

  it("sends the whole price table when a price is added", async () => {
    const send = vi.spyOn(usageSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await wrapper.get('[data-test="price-add"]').trigger("click");
    const rows = wrapper.findAll('[data-test="price"]');
    await rows[1].get('[data-test="price-model"]').setValue(" opus ");
    await rows[1].get('[data-test="price-input"]').setValue("15");
    await rows[1].get('[data-test="price-output"]').setValue("75");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(send).toHaveBeenCalledWith({ pricing: { models: { sonnet: { input: 3, output: 15 }, opus: { input: 15, output: 75 } } } });
    wrapper.unmount();
  });

  it("blocks an unnamed or repeated price and removes one", async () => {
    const wrapper = await mounted();
    await wrapper.get('[data-test="price-add"]').trigger("click");
    expect(wrapper.get('[data-test="problem"]').text()).toContain("model name");
    expect(save(wrapper).attributes("disabled")).toBeDefined();
    const rows = wrapper.findAll('[data-test="price"]');
    await rows[1].get('[data-test="price-model"]').setValue("SONNET");
    await rows[1].get('[data-test="price-input"]').setValue("1");
    await rows[1].get('[data-test="price-output"]').setValue("1");
    expect(wrapper.get('[data-test="problem"]').text()).toContain("different");
    await rows[1].get('[data-test="price-remove"]').trigger("click");
    expect(wrapper.find('[data-test="problem"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows the refusal", async () => {
    vi.spyOn(usageSettingsClient, "save").mockRejectedValue(new Error("usage.auto_summarize_ratio must be above 0 and at most 1"));
    const wrapper = await mounted();
    await wrapper.get('[data-test="auto_summarize_ratio"]').setValue("2");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("at most 1");
    wrapper.unmount();
  });
});
