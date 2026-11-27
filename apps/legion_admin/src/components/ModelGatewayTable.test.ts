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
  presets: { ollama: { provider: "openai", auth: "key", api: "chat", label: "Ollama", models_url: "https://ollama.com/library", base_url: "http://host.docker.internal:11434/v1", model: "qwen", models: { light: "qwen-small" }, descriptions: { light: "quick" } } },
  form: {
    providers: { openai: { key: [["api_key", "API key", true, false], ["base_url", "Base address", false, false]] }, scuti: { "": [["url", "Model service address", false, true]] } },
    choices: { api: ["chat", "responses"] },
  },
};

it("adds a chat gateway from a preset and sends only what the form holds", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const save = vi.spyOn(agentsAdminClient, "saveModelGateway").mockResolvedValue({ id: "ollama", provider: "openai" });
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  expect(wrapper.text()).toContain("No gateway is saved yet.");
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="preset"]').setValue("ollama");
  await wrapper.get('[data-test="preset"]').trigger("change");
  expect((wrapper.get('[data-test="id"]').element as HTMLInputElement).value).toBe("ollama");
  expect((wrapper.get('[data-test="tier-light"]').element as HTMLInputElement).value).toBe("qwen-small");
  expect((wrapper.get('[data-test="note-light"]').element as HTMLInputElement).value).toBe("quick");
  await wrapper.get('[data-test="tier-heavy"]').setValue("qwen-big");
  await wrapper.get('[data-test="note-heavy"]').setValue("  audits ");
  await wrapper.get('[data-test="api_key"]').setValue("secret");
  await wrapper.get("form").trigger("submit");
  wrapper.findComponent({ name: "RecordDrawer" }).vm.$emit("save");
  await flushPromises();
  expect(save).toHaveBeenCalledWith("conversation", "ollama", expect.objectContaining({
    provider: "openai", auth: "key", api: "chat", model: "qwen", label: "Ollama", base_url: "http://host.docker.internal:11434/v1", api_key: "secret",
    models: { light: "qwen-small", heavy: "qwen-big" }, descriptions: { light: "quick", heavy: "audits" },
  }));
  wrapper.unmount();
});

it("refuses a name the gateway would not accept before asking to save", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="id"]').setValue("Bad Name");
  await wrapper.get("form").trigger("submit");
  expect(wrapper.get('[data-test="error"]').text()).toContain("lowercase");
  wrapper.unmount();
});

it("splits a chat gateway into Connection and Models tabs and returns to Connection for a missing field", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  expect(wrapper.get('[data-test="tab-models"]').attributes("disabled")).toBeDefined();
  await wrapper.get('[data-test="preset"]').setValue("ollama");
  await wrapper.get('[data-test="preset"]').trigger("change");
  expect(wrapper.get('[data-test="tab-models"]').attributes("disabled")).toBeUndefined();
  await wrapper.get('[data-test="tab-models"]').trigger("click");
  expect(wrapper.get('[data-test="models-link"]').attributes("href")).toBe("https://ollama.com/library");
  expect(wrapper.get('[data-test="tab-models"]').attributes("aria-selected")).toBe("true");
  expect(wrapper.get("#conversation-panel-models").isVisible()).toBe(true);
  expect(wrapper.get("#conversation-panel-connection").isVisible()).toBe(false);
  await wrapper.get('[data-test="id"]').setValue("Bad Name");
  await wrapper.get("form").trigger("submit");
  expect(wrapper.get('[data-test="tab-connection"]').attributes("aria-selected")).toBe("true");
  expect(wrapper.get('[data-test="error"]').text()).toContain("lowercase");
  wrapper.unmount();
});

it("tests the form as filled in before it is saved", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const test = vi.spyOn(agentsAdminClient, "testModelGateway").mockResolvedValue({ ok: false, code: "401", message: "The key was refused." } as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="preset"]').setValue("ollama");
  await wrapper.get('[data-test="preset"]').trigger("change");
  await wrapper.get('[data-test="api_key"]').setValue("typed-key");
  await wrapper.get('[data-test="test-draft"]').trigger("click");
  await flushPromises();
  expect(test).toHaveBeenCalledWith("conversation", "ollama", expect.objectContaining({ provider: "openai", api_key: "typed-key" }));
  expect(wrapper.get('[data-test="draft-code"]').text()).toBe("401");
  expect(wrapper.get('[data-test="draft-result"]').text()).toContain("The key was refused.");
  wrapper.unmount();
});

it("opens the Models tab when the default model is missing", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue({ ...list, presets: { free: { provider: "openai", auth: "key", api: "chat", label: "Free", base_url: "http://host.docker.internal:29652/v1", model: "" } } } as never);
  const test = vi.spyOn(agentsAdminClient, "testModelGateway");
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="preset"]').setValue("free");
  await wrapper.get('[data-test="preset"]').trigger("change");
  await wrapper.get('[data-test="test-draft"]').trigger("click");
  expect(wrapper.get('[data-test="tab-models"]').attributes("aria-selected")).toBe("true");
  expect(wrapper.get('[data-test="draft-result"]').text()).toContain("default model");
  await wrapper.get('[data-test="tab-connection"]').trigger("click");
  await wrapper.get("form").trigger("submit");
  expect(wrapper.get('[data-test="tab-models"]').attributes("aria-selected")).toBe("true");
  expect(wrapper.get('[data-test="error"]').text()).toContain("default model");
  expect(test).not.toHaveBeenCalled();
  wrapper.unmount();
});

it("will not save a new chat gateway before a preset is chosen", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="type"]').setValue("openai");
  await wrapper.get('[data-test="id"]').setValue("mine");
  await wrapper.get("form").trigger("submit");
  expect(wrapper.get('[data-test="error"]').text()).toContain("Choose a preset first");
  wrapper.unmount();
});

it("offers the presets in groups under the label Preset", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue({
    ...list,
    presets: {
      gpt: { provider: "openai", label: "GPT" }, claude: { provider: "anthropic", label: "Claude" },
      bedrock: { provider: "anthropic", label: "AWS Bedrock" }, mini: { provider: "scuti", label: "CNV_Mini" },
    },
  } as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  expect(wrapper.get('label[for="conversation-preset"]').text()).toBe("Preset");
  const groups = wrapper.findAll("optgroup");
  expect(groups.map((group) => group.attributes("label"))).toEqual(["Anthropic protocol", "OpenAI protocol", "Model services"]);
  expect(groups[0]!.findAll("option").map((option) => option.text())).toEqual(["AWS Bedrock", "Claude"]);
  wrapper.unmount();
});

it("shows which gateways are trusted, takes the preset's default and sends the switch", async () => {
  const withTrust = {
    ...list,
    gateways: [{ id: "claude", provider: "anthropic", trusted: true }, { id: "omniroute", provider: "anthropic", trusted: false }],
    presets: { ollama: { ...list.presets.ollama, trusted: true } },
  };
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(withTrust as never);
  const save = vi.spyOn(agentsAdminClient, "saveModelGateway").mockResolvedValue({ id: "ollama", provider: "openai" });
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  expect(wrapper.get('[data-test="trust-claude"]').text()).toBe("Trusted");
  expect(wrapper.get('[data-test="trust-omniroute"]').text()).toBe("Not trusted");
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="preset"]').setValue("ollama");
  await wrapper.get('[data-test="preset"]').trigger("change");
  const toggle = wrapper.get('[data-test="trusted"]');
  expect((toggle.element as HTMLInputElement).checked).toBe(true);
  await toggle.setValue(false);
  await wrapper.get('[data-test="api_key"]').setValue("secret");
  await wrapper.get("form").trigger("submit");
  wrapper.findComponent({ name: "RecordDrawer" }).vm.$emit("save");
  await flushPromises();
  expect(save).toHaveBeenCalledWith("conversation", "ollama", expect.objectContaining({ trusted: false }));
  wrapper.unmount();
});

it("shows a chat gateway's health: cooling down, recent failures, or none", async () => {
  const health = (cooldown_seconds: number, failures_24h: number) => ({ cooldown_seconds, failures_24h, last_kind: failures_24h ? "quota" : null });
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue({
    ...list,
    gateways: [
      { id: "a", provider: "openai", health: health(300, 2) },
      { id: "b", provider: "openai", health: health(0, 1) },
      { id: "c", provider: "openai", health: health(0, 0) },
    ],
  } as never);
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  expect(wrapper.get('[data-test="health-a"]').text()).toContain("Cooling down for 5 min");
  expect(wrapper.get('[data-test="health-b"]').text()).toBe("1 failure in 24 hours");
  expect(wrapper.get('[data-test="health-c"]').text()).toBe("No failures in 24 hours");
  wrapper.unmount();
});

it("saves the Hears audio switch for an OpenAI-compatible chat gateway", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockResolvedValue(list as never);
  const save = vi.spyOn(agentsAdminClient, "saveModelGateway").mockResolvedValue({ id: "ollama", provider: "openai" });
  const wrapper = mount(ModelGatewayTable, { attachTo: document.body, props: { kind: "conversation", title: "Chat models", help: "Help" }, global: { stubs: { Teleport: true } } });
  await flushPromises();
  await wrapper.get('[data-test="add-conversation"]').trigger("click");
  await wrapper.get('[data-test="preset"]').setValue("ollama");
  await wrapper.get('[data-test="preset"]').trigger("change");
  const toggle = wrapper.get('[data-test="audio"]');
  expect((toggle.element as HTMLInputElement).checked).toBe(false);
  await toggle.setValue(true);
  await wrapper.get('[data-test="api_key"]').setValue("secret");
  await wrapper.get("form").trigger("submit");
  wrapper.findComponent({ name: "RecordDrawer" }).vm.$emit("save");
  await flushPromises();
  expect(save).toHaveBeenCalledWith("conversation", "ollama", expect.objectContaining({ capabilities: { audio: true } }));
  wrapper.unmount();
});
