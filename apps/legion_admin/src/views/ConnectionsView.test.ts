import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeAll, expect, it, vi } from "vitest";
import { agentsAdminClient } from "../api/AgentsAdminClient";
import ConnectionsView from "./ConnectionsView.vue";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});

it("keeps the panels independently searchable and preserves a working panel after a partial failure", async () => {
  vi.spyOn(agentsAdminClient, "modelGateways").mockImplementation(async (kind) => {
    if (kind === "decision") throw new Error("DecisionGateway unavailable");
    return { gateways: [{ id: "claude", provider: "anthropic", label: "Text model", model: "claude-test" }], presets: {}, form: { providers: {}, choices: { api: [] } } };
  });
  vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({ main: { label: "Armory", description: "Tools", url: "https://armory.test/mcp", transport: "http" } });
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/connections", component: ConnectionsView }] });
  await router.push("/connections");
  const wrapper = mount(ConnectionsView, { attachTo: document.body, global: { plugins: [router], stubs: { Teleport: true } } });
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toBe("DecisionGateway unavailable");
  const models = wrapper.get('section[aria-labelledby="model-gateways"]');
  const servers = wrapper.get("#mcp-servers");
  expect(models.text()).toContain("Text model");
  expect(servers.text()).toContain("Armory");
  await servers.get('input[type="search"]').setValue("missing");
  expect(servers.text()).toContain("No servers match");
  expect(models.get(".admin-row-button").isVisible()).toBe(true);
  await models.get('input[type="search"]').setValue("missing");
  expect(models.find(".admin-row-button").exists()).toBe(false);
  expect(models.get('[role="alert"]').text()).toContain("DecisionGateway unavailable");
  wrapper.unmount();
});
