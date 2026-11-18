import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import ConnectionsView from "./ConnectionsView.vue";
import { connectionsClient } from "../api/ConnectionsClient";

afterEach(() => vi.restoreAllMocks());
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});

it("shows the three connection classes and checks a saved REST transport", async () => {
  vi.spyOn(connectionsClient, "list").mockResolvedValue([{
    name: "bard", class: "required", label: "Bard", enabled: true, description: "",
    web_url: null, mcp: null, ready: true, reason: null,
    rest: { base_url: "http://bard", auth: { kind: "token", configured: true } },
  }]);
  vi.spyOn(connectionsClient, "personalCount").mockResolvedValue(2);
  const probe = vi.spyOn(connectionsClient, "test").mockResolvedValue({ ok: true, message: "REST is ready." });
  const wrapper = mount(ConnectionsView);
  await flushPromises();
  expect(wrapper.text()).toContain("Required");
  expect(wrapper.text()).toContain("Server-sided optional");
  expect(wrapper.text()).toContain("Client-sided");
  expect(wrapper.text()).toContain("2 personal connections");
  expect(wrapper.text()).toContain("Token set");
  await wrapper.get('button[aria-label="Test Bard REST"]').trigger("click");
  await flushPromises();
  expect(probe).toHaveBeenCalledWith("bard", "rest");
  expect(wrapper.text()).toContain("REST is ready.");
  await wrapper.get('button[aria-label="Edit Bard"]').trigger("click");
  expect(wrapper.get('input[type="password"]').element).toHaveProperty("value", "");
  wrapper.unmount();
});

it("adds a REST-only optional connection without putting credentials in the result", async () => {
  vi.spyOn(connectionsClient, "list").mockResolvedValue([]);
  vi.spyOn(connectionsClient, "personalCount").mockResolvedValue(0);
  const create = vi.spyOn(connectionsClient, "create").mockResolvedValue({
    name: "lens", class: "server", label: "Lens", enabled: true, description: "",
    web_url: null, mcp: null, ready: true, reason: null,
    rest: { base_url: "http://lens", auth: { kind: "none", configured: false } },
  });
  const wrapper = mount(ConnectionsView);
  await flushPromises();
  await wrapper.findAll("button").find(button => button.text() === "Add connection")!.trigger("click");
  await wrapper.get("form input[required]").setValue("Lens");
  await wrapper.findAll('form input[type="url"]').at(-1)!.setValue("http://lens");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(create).toHaveBeenCalledWith(expect.objectContaining({
    label: "Lens", mcp: null, rest: { base_url: "http://lens", auth: { kind: "none" } },
  }));
  expect(wrapper.text()).toContain("Lens");
  wrapper.unmount();
});

it("preserves an unchanged migrated MCP transport when configuring REST", async () => {
  const bard = {
    name: "bard", class: "required" as const, label: "Bard", enabled: true, description: "",
    web_url: null, ready: false, reason: "Set up REST.",
    mcp: { url: null, auth: { kind: "token" as const, configured: true } }, rest: null,
  };
  vi.spyOn(connectionsClient, "list").mockResolvedValue([bard]);
  vi.spyOn(connectionsClient, "personalCount").mockResolvedValue(0);
  const update = vi.spyOn(connectionsClient, "update").mockResolvedValue(bard);
  const wrapper = mount(ConnectionsView);
  await flushPromises();
  await wrapper.get('button[aria-label="Edit Bard"]').trigger("click");
  await wrapper.findAll('form input[type="url"]').at(-1)!.setValue("http://bard");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(update.mock.calls[0]?.[1]).not.toHaveProperty("mcp");
  wrapper.unmount();
});
