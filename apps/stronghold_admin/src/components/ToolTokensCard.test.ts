import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toolTokensClient, type ToolService } from "../api/ToolTokensClient";
import ToolTokensCard from "./ToolTokensCard.vue";

const SERVICES: ToolService[] = [
  { name: "bard", label: "Bard", has_token: true, stored: true },
  { name: "scribe", label: "Scribe", has_token: false, stored: false },
];

beforeEach(() => {
  vi.spyOn(toolTokensClient, "list").mockResolvedValue(SERVICES);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(ToolTokensCard, { props: { kind: "own", title: "Tool services" }, attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const token = (wrapper: Awaited<ReturnType<typeof mounted>>, name: string) => wrapper.get(`[data-test="row-${name}"] [data-test="token"]`);

describe("ToolTokensCard", () => {
  it("says which services have a token in use and never shows a token", async () => {
    const wrapper = await mounted();
    expect(token(wrapper, "bard").attributes("placeholder")).toContain("A token is in use");
    expect(token(wrapper, "scribe").attributes("placeholder")).toBe("No token yet");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("sends only the tokens typed", async () => {
    const save = vi.spyOn(toolTokensClient, "save").mockResolvedValue(SERVICES);
    const wrapper = await mounted();
    await token(wrapper, "scribe").setValue("sc-new");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("own", { scribe: "sc-new" });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next request");
    wrapper.unmount();
  });

  it("removes a saved token with null and can take it back before saving", async () => {
    const save = vi.spyOn(toolTokensClient, "save").mockResolvedValue(SERVICES);
    const wrapper = await mounted();
    const remove = wrapper.get('[data-test="row-bard"] [data-test="remove"]');
    await remove.trigger("click");
    await remove.trigger("click");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    await remove.trigger("click");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("own", { bard: null });
    wrapper.unmount();
  });

  it("shows the refusal", async () => {
    vi.spyOn(toolTokensClient, "save").mockRejectedValue(new Error("Scribe: paste the token, or remove it."));
    const wrapper = await mounted();
    await token(wrapper, "scribe").setValue("x");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("paste the token");
    wrapper.unmount();
  });
});
