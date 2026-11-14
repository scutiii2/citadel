import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import GatewayConnectionCard from "./GatewayConnectionCard.vue";

const SAVED = { url: "http://conversationgateway:29407", has_token: true };

const store = vi.fn();

async function open(view = SAVED) {
  const wrapper = mount(GatewayConnectionCard, {
    props: { id: "gw", title: "ConversationGateway", example: SAVED.url, load: async () => view, store },
  });
  await flushPromises();
  return wrapper;
}

afterEach(() => store.mockReset());

describe("GatewayConnectionCard", () => {
  it("shows the saved address and never the token", async () => {
    const wrapper = await open();
    expect((wrapper.get('[data-test="url"]').element as HTMLInputElement).value).toBe(SAVED.url);
    expect((wrapper.get('[data-test="token"]').element as HTMLInputElement).value).toBe("");
    expect(wrapper.get('[data-test="token-state"]').text()).toContain("A token is saved");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
  });

  it("sends only the changed address, so the saved token is kept", async () => {
    const set = store.mockResolvedValue({ url: "http://other:29407", has_token: true });
    const wrapper = await open();
    await wrapper.get('[data-test="url"]').setValue("http://other:29407");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(set).toHaveBeenCalledWith({ url: "http://other:29407" });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("Saved");
  });

  it("sends a new token and clears the field afterwards", async () => {
    const set = store.mockResolvedValue(SAVED);
    const wrapper = await open({ url: SAVED.url, has_token: false });
    expect(wrapper.find('[data-test="clear-token"]').exists()).toBe(false);
    await wrapper.get('[data-test="token"]').setValue("cg_new");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(set).toHaveBeenCalledWith({ token: "cg_new" });
    expect((wrapper.get('[data-test="token"]').element as HTMLInputElement).value).toBe("");
  });

  it("removes the token and shows a refusal from the server", async () => {
    const set = store
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

  it("labels its fields with its own id, so two cards can share a page", async () => {
    const wrapper = await open();
    expect(wrapper.get("label").attributes("for")).toBe("gw-url");
    expect(wrapper.get("h2").text()).toBe("ConversationGateway");
  });
});
