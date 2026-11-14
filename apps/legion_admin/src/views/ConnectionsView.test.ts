import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import ConnectionsView from "./ConnectionsView.vue";

const SAVED = { url: "http://conversationgateway:29407", has_token: true };

async function open(view = SAVED) {
  vi.spyOn(agentsAdminClient, "gatewaySettings").mockResolvedValue(view);
  const wrapper = mount(ConnectionsView);
  await flushPromises();
  return wrapper;
}

afterEach(() => vi.restoreAllMocks());

describe("ConnectionsView", () => {
  it("shows the saved address and never the token", async () => {
    const wrapper = await open();
    expect((wrapper.get('[data-test="url"]').element as HTMLInputElement).value).toBe(SAVED.url);
    expect((wrapper.get('[data-test="token"]').element as HTMLInputElement).value).toBe("");
    expect(wrapper.get('[data-test="token-state"]').text()).toContain("A token is saved");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
  });

  it("sends only the changed address, so the saved token is kept", async () => {
    const set = vi.spyOn(agentsAdminClient, "setGatewaySettings").mockResolvedValue({ url: "http://other:29407", has_token: true });
    const wrapper = await open();
    await wrapper.get('[data-test="url"]').setValue("http://other:29407");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(set).toHaveBeenCalledWith({ url: "http://other:29407" });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("Saved");
  });

  it("sends a new token and clears the field afterwards", async () => {
    const set = vi.spyOn(agentsAdminClient, "setGatewaySettings").mockResolvedValue(SAVED);
    const wrapper = await open({ url: SAVED.url, has_token: false });
    expect(wrapper.find('[data-test="clear-token"]').exists()).toBe(false);
    await wrapper.get('[data-test="token"]').setValue("cg_new");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(set).toHaveBeenCalledWith({ token: "cg_new" });
    expect((wrapper.get('[data-test="token"]').element as HTMLInputElement).value).toBe("");
  });

  it("removes the token and shows a refusal from the server", async () => {
    const set = vi.spyOn(agentsAdminClient, "setGatewaySettings")
      .mockResolvedValueOnce({ url: SAVED.url, has_token: false })
      .mockRejectedValueOnce(new Error("url must be an http(s) address"));
    const wrapper = await open();
    await wrapper.get('[data-test="clear-token"]').trigger("click");
    await flushPromises();
    expect(set).toHaveBeenCalledWith({ token: "" });
    expect(wrapper.get('[data-test="token-state"]').text()).toContain("No token is saved");
    await wrapper.get('[data-test="url"]').setValue("http://x");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toBe("url must be an http(s) address");
  });
});
