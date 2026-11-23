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
  const chat = wrapper.get("#conversation-gateways");
  const decision = wrapper.get("#decision-gateways");
  const servers = wrapper.get("#mcp-servers");
  expect(decision.get('[role="alert"]').text()).toContain("DecisionGateway unavailable");
  expect(chat.text()).toContain("Text model");
  expect(servers.text()).toContain("Armory");
  await servers.get('input[type="search"]').setValue("missing");
  expect(servers.text()).toContain("No servers match");
  expect(chat.get(".admin-row-button").isVisible()).toBe(true);
  await chat.get('input[type="search"]').setValue("missing");
  expect(chat.find(".admin-row-button").exists()).toBe(false);
  expect(chat.get('[data-test="empty-conversation"]').text()).toContain("No gateways match");
  wrapper.unmount();
});
