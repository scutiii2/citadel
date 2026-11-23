import { flushPromises, mount } from "@vue/test-utils";
import { beforeAll, expect, it, vi } from "vitest";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import ModelGatewayTable from "./ModelGatewayTable.vue";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});

const list = {
  gateways: [],
  presets: { ollama: { provider: "openai", auth: "key", api: "chat", label: "Ollama", base_url: "http://host.docker.internal:11434/v1", model: "qwen" } },
  form: {
    providers: { openai: { key: [["api_key", "API key", true, false], ["base_url", "Base address", false, false]] }, scuti: { "": [["url", "Model service address", false, true]] } },
    choices: { api: ["chat", "responses"] },
  },
};

it("adds a chat gateway from a preset and sends only what the form holds", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const save = vi.spyOn(agentsAdminClient, "saveModelGateway").mockResolvedValue({ id: "ollama", provider: "openai" });
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", search: "" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  expect(wrapper.text()).toContain("No chat models gateway is saved yet.");
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="preset"]').setValue("ollama");
  await wrapper.get('[data-test="preset"]').trigger("change");
  expect((wrapper.get('[data-test="id"]').element as HTMLInputElement).value).toBe("ollama");
  await wrapper.get('[data-test="api_key"]').setValue("secret");
  await wrapper.get("form").trigger("submit");
  wrapper.findComponent({ name: "RecordDrawer" }).vm.$emit("save");
  await flushPromises();
  expect(save).toHaveBeenCalledWith("conversation", "ollama", expect.objectContaining({
    provider: "openai", auth: "key", api: "chat", model: "qwen", label: "Ollama", base_url: "http://host.docker.internal:11434/v1", api_key: "secret",
  }));
  wrapper.unmount();
});

it("refuses a name the gateway would not accept before asking to save", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", search: "" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="id"]').setValue("Bad Name");
  await wrapper.get("form").trigger("submit");
  expect(wrapper.get('[data-test="error"]').text()).toContain("lowercase");
  wrapper.unmount();
});
