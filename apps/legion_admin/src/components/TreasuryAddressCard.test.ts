import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import TreasuryAddressCard from "./TreasuryAddressCard.vue";

beforeEach(() => {
  vi.spyOn(agentsAdminClient, "treasuryAddress").mockResolvedValue({ url: "http://127.0.0.1:29602", stored: false });
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(TreasuryAddressCard, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}

describe("TreasuryAddressCard", () => {
  it("shows the address in use and says when it is not saved here", async () => {
    const wrapper = await mounted();
    expect((wrapper.get('[data-test="url"]').element as HTMLInputElement).value).toBe("http://127.0.0.1:29602");
    expect(wrapper.text()).toContain("Not saved here");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-test="reset"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("saves a new address, trimmed, and then offers to go back", async () => {
    const save = vi.spyOn(agentsAdminClient, "setTreasuryAddress").mockResolvedValue({ url: "http://treasury:29602", stored: true });
    const wrapper = await mounted();
    await wrapper.get('[data-test="url"]').setValue(" http://treasury:29602 ");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("http://treasury:29602");
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next request");
    expect(wrapper.find('[data-test="reset"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("goes back to the default with null", async () => {
    vi.spyOn(agentsAdminClient, "treasuryAddress").mockResolvedValue({ url: "http://treasury:29602", stored: true });
    const save = vi.spyOn(agentsAdminClient, "setTreasuryAddress").mockResolvedValue({ url: "http://127.0.0.1:29602", stored: false });
    const wrapper = await mounted();
    await wrapper.get('[data-test="reset"]').trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledWith(null);
    wrapper.unmount();
  });

  it("shows the refusal", async () => {
    vi.spyOn(agentsAdminClient, "setTreasuryAddress").mockRejectedValue(new Error("url must be an http(s) address"));
    const wrapper = await mounted();
    await wrapper.get('[data-test="url"]').setValue("http://x");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("http(s)");
    wrapper.unmount();
  });
});
