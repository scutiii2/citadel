import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsAdminClient, type McpServer } from "../api/AgentsAdminClient";
import ServersView from "./ServersView.vue";

const MAIN: McpServer = { label: "armory", transport: "http", url: "http://127.0.0.1:29600/mcp",
  auth: { type: "header", header_name: "X-Token", has_value: true } };

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
});
beforeEach(() => {
  vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({ main: MAIN });
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(ServersView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}

describe("ServersView", () => {
  it("lists the saved servers and tells an empty install how to start", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="row-main"]').text()).toContain("http://127.0.0.1:29600/mcp");
    wrapper.unmount();

    vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({});
    const empty = await mounted();
    expect(empty.get('[data-test="empty"]').text()).toContain("Add Armory");
    empty.unmount();
  });

  it("adds a server and sends the typed entry", async () => {
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "docs" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="id"]').setValue("docs");
    await wrapper.get('[data-test="label"]').setValue("Docs");
    await wrapper.get('[data-test="url"]').setValue("http://docs:1/mcp");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("docs", { label: "Docs", description: "", transport: "http", url: "http://docs:1/mcp" });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next start");
    wrapper.unmount();
  });

  it("keeps a saved token when it is not retyped", async () => {
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "main" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="edit"]').trigger("click");
    expect(wrapper.get('[data-test="id"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    const sent = save.mock.calls[0][1];
    expect(sent.auth).toEqual({ type: "header", header_name: "X-Token" });
    wrapper.unmount();
  });

  it("shows the refusal of the server", async () => {
    vi.spyOn(agentsAdminClient, "saveServer").mockRejectedValue(new Error("transport 'http' requires 'url'"));
    const wrapper = await mounted();
    await wrapper.get('[data-test="edit"]').trigger("click");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("requires 'url'");
    wrapper.unmount();
  });
});
