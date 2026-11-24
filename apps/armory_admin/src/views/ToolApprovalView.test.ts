import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/http";
import { toolApprovalClient } from "../api/ToolApprovalClient";
import ToolApprovalView from "./ToolApprovalView.vue";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});
afterEach(() => vi.restoreAllMocks());

async function mounted(on = false) {
  vi.spyOn(toolApprovalClient, "get").mockResolvedValue({ force_tool_approval: on });
  const wrapper = mount(ToolApprovalView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const flip = async (wrapper: Awaited<ReturnType<typeof mounted>>) => {
  const box = wrapper.get('[data-test="force"]');
  (box.element as HTMLInputElement).checked = !(box.element as HTMLInputElement).checked;
  await box.trigger("change");
};

describe("ToolApprovalView", () => {
  it("shows the stored value and a flip is only a draft until Save", async () => {
    const wrapper = await mounted(false);
    const set = vi.spyOn(toolApprovalClient, "set").mockResolvedValue({ force_tool_approval: true });
    expect(wrapper.find('[data-test="unsaved"]').exists()).toBe(false);

    await flip(wrapper);
    expect(wrapper.get('[data-test="unsaved"]').text()).toContain("on");
    expect(set).not.toHaveBeenCalled();

    await wrapper.get('button[aria-label="Save tool approval changes"]').trigger("click");
    await flushPromises();
    expect(set).toHaveBeenCalledWith(true);
    expect(wrapper.find('[data-test="unsaved"]').exists()).toBe(false);
    expect(wrapper.get('[data-test="notice"]').text()).toContain("Saved");
  });

  it("keeps the draft and shows the code when saving fails", async () => {
    const wrapper = await mounted(true);
    vi.spyOn(toolApprovalClient, "set").mockRejectedValue(new ApiError(502, "mcp_server is unreachable"));

    await flip(wrapper);
    await wrapper.get('button[aria-label="Save tool approval changes"]').trigger("click");
    await flushPromises();

    expect(wrapper.get(".action-message.error").text()).toContain("mcp_server is unreachable");
    expect(wrapper.get(".action-message.error .code").text()).toBe("502");
    expect(wrapper.find('[data-test="unsaved"]').exists()).toBe(true);
  });

  it("offers Retry when the value cannot be read", async () => {
    const get = vi.spyOn(toolApprovalClient, "get").mockRejectedValueOnce(new ApiError(502, "mcp_server is unreachable"));
    const wrapper = mount(ToolApprovalView, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.find('[data-test="force"]').exists()).toBe(false);

    get.mockResolvedValue({ force_tool_approval: true });
    await wrapper.get("button.link-btn").trigger("click");
    await flushPromises();
    expect((wrapper.get('[data-test="force"]').element as HTMLInputElement).checked).toBe(true);
  });
});
