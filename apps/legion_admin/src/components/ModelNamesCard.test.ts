import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsAdminClient, type ModelName } from "../api/AgentsAdminClient";
import ModelNamesCard from "./ModelNamesCard.vue";

const MODELS: ModelName[] = [
  { name: "VLLM_MODEL_DEFAULT", value: "llama-3", stored: true },
  { name: "VLLM_MODEL_LIGHT", value: "", stored: false },
];

beforeEach(() => {
  vi.spyOn(agentsAdminClient, "modelNames").mockResolvedValue(MODELS);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(ModelNamesCard, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const input = (wrapper: Awaited<ReturnType<typeof mounted>>, name: string) => wrapper.get(`[data-test="row-${name}"] [data-test="input"]`);

describe("ModelNamesCard", () => {
  it("lists every open name with its saved value and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((input(wrapper, "VLLM_MODEL_DEFAULT").element as HTMLInputElement).value).toBe("llama-3");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("sends only the names that changed, trimmed", async () => {
    const save = vi.spyOn(agentsAdminClient, "setModelNames").mockResolvedValue(MODELS);
    const wrapper = await mounted();
    await input(wrapper, "VLLM_MODEL_LIGHT").setValue(" tiny ");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ VLLM_MODEL_LIGHT: "tiny" });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next starts");
    wrapper.unmount();
  });

  it("removes a saved name with null", async () => {
    const save = vi.spyOn(agentsAdminClient, "setModelNames").mockResolvedValue(MODELS);
    const wrapper = await mounted();
    await wrapper.get('[data-test="row-VLLM_MODEL_DEFAULT"] [data-test="remove"]').trigger("click");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ VLLM_MODEL_DEFAULT: null });
    wrapper.unmount();
  });

  it("shows the refusal", async () => {
    vi.spyOn(agentsAdminClient, "setModelNames").mockRejectedValue(new Error("Unknown model name: X."));
    const wrapper = await mounted();
    await input(wrapper, "VLLM_MODEL_LIGHT").setValue("a");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Unknown model name");
    wrapper.unmount();
  });
});
