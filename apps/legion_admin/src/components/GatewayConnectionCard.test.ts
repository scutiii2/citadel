import { flushPromises, mount } from "@vue/test-utils";
import { beforeAll, describe, expect, it, vi } from "vitest";
import GatewayConnectionCard from "./GatewayConnectionCard.vue";

const SAVED = { url: "http://conversationgateway:29407", has_token: true };

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});

async function open(store = vi.fn(), view = SAVED) {
  const wrapper = mount(GatewayConnectionCard, {
    props: { id: "gw", title: "ConversationGateway", example: SAVED.url, search: "", load: async () => view, store },
    global: { stubs: { Teleport: true } },
  });
  await flushPromises();
  await wrapper.get(".admin-row-button").trigger("click");
  return wrapper;
}

async function edit(wrapper: Awaited<ReturnType<typeof open>>) {
  await wrapper.get('dialog[open] [data-test="edit"]').trigger("click");
}

async function confirmSave(wrapper: Awaited<ReturnType<typeof open>>) {
  await wrapper.get("form").trigger("submit");
  await wrapper.get('dialog[aria-label="Save changes?"][open] .confirm').trigger("click");
  await flushPromises();
}

describe("GatewayConnectionCard", () => {
  it("shows address and token presence, with an empty token editor", async () => {
    const wrapper = await open();
    expect(wrapper.get('[data-test="token-state"]').text()).toContain("A token is saved");
    await edit(wrapper);
    expect(wrapper.get<HTMLInputElement>('[data-test="url"]').element.value).toBe(SAVED.url);
    expect(wrapper.get<HTMLInputElement>('[data-test="token"]').element.value).toBe("");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('label[for="gw-url"]').text()).toBe("Connection URL");
    wrapper.unmount();
  });

  it("sends only changed fields and never sends the untouched token", async () => {
    const result = { ...SAVED, url: "http://other:29407", description: "Chat models" };
    const store = vi.fn().mockResolvedValue(result);
    const wrapper = await open(store);
    await edit(wrapper);
    await wrapper.get('[data-test="url"]').setValue(result.url);
    await wrapper.get('[data-test="description"]').setValue(" Chat models ");
    await wrapper.get("form").trigger("submit");
    expect(store).not.toHaveBeenCalled();
    await wrapper.get('dialog[aria-label="Save changes?"][open] .confirm').trigger("click");
    await flushPromises();
    expect(store).toHaveBeenCalledWith({ url: result.url, description: result.description });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("within half a minute");
    wrapper.unmount();
  });

  it("sets a token and clears the password field after success", async () => {
    const store = vi.fn().mockResolvedValue(SAVED);
    const wrapper = await open(store, { ...SAVED, has_token: false });
    await edit(wrapper);
    expect(wrapper.find('[data-test="clear-token"]').exists()).toBe(false);
    await wrapper.get('[data-test="token"]').setValue("cg_new");
    await confirmSave(wrapper);
    expect(store).toHaveBeenCalledWith({ token: "cg_new" });
    await edit(wrapper);
    expect(wrapper.get<HTMLInputElement>('[data-test="token"]').element.value).toBe("");
    wrapper.unmount();
  });

  it("keeps a rejected draft and sends explicit token removal on retry", async () => {
    const store = vi.fn().mockRejectedValueOnce(new Error("Gateway unavailable")).mockResolvedValueOnce({ ...SAVED, has_token: false });
    const wrapper = await open(store);
    await edit(wrapper);
    await wrapper.get('[data-test="clear-token"]').trigger("click");
    await confirmSave(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toBe("Gateway unavailable");
    expect(wrapper.get('[data-test="clear-token"]').attributes("aria-pressed")).toBe("true");
    await confirmSave(wrapper);
    expect(store).toHaveBeenLastCalledWith({ token: "" });
    expect(wrapper.get('[data-test="token-state"]').text()).toContain("No token is saved");
    wrapper.unmount();
  });
});
