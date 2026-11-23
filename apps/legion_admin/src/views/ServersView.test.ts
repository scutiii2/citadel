import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsAdminClient, type McpServer, type OriginLookup } from "../api/AgentsAdminClient";
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

async function edit(wrapper: Awaited<ReturnType<typeof mounted>>, id: string) {
  await wrapper.get(`[data-test="row-${id}"] .admin-row-button`).trigger("click");
  await wrapper.get('[data-test="edit"]').trigger("click");
}

async function submit(wrapper: Awaited<ReturnType<typeof mounted>>) {
  await wrapper.get('[data-test="form"]').trigger("submit");
  await wrapper.get('dialog[aria-label="Save changes?"][open] button.confirm').trigger("click");
  await flushPromises();
}

describe("ServersView", () => {
  it("lists the saved servers and tells an empty install how to start", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="row-main"]').text()).toContain("http://127.0.0.1:29600/mcp");
    wrapper.unmount();

    vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({});
    const empty = await mounted();
    expect(empty.get('[data-test="empty"]').text()).toContain("No MCP servers");
    empty.unmount();
  });

  it("adds a server and sends the typed entry", async () => {
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "docs" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="id"]').setValue("docs");
    await wrapper.get('[data-test="label"]').setValue("Docs");
    await wrapper.get('[data-test="mode"]').setValue("direct");
    await wrapper.get('[data-test="url"]').setValue("http://docs:1/mcp");
    await submit(wrapper);
    expect(save).toHaveBeenCalledWith("docs", { label: "Docs", description: "", transport: "http", url: "http://docs:1/mcp" });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next start");
    wrapper.unmount();
  });

  it("keeps a saved token when it is not retyped", async () => {
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "main" });
    const wrapper = await mounted();
    await edit(wrapper, "main");
    expect(wrapper.get('[data-test="id"]').attributes("disabled")).toBeDefined();
    await submit(wrapper);
    const sent = save.mock.calls[0][1];
    expect(sent.auth).toEqual({ type: "header", header_name: "X-Token" });
    wrapper.unmount();
  });

  it("shows the refusal of the server", async () => {
    vi.spyOn(agentsAdminClient, "saveServer").mockRejectedValue(new Error("transport 'http' requires 'url'"));
    const wrapper = await mounted();
    await edit(wrapper, "main");
    await submit(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toContain("requires 'url'");
    wrapper.unmount();
  });

  it("fills the name of a known address and locks it", async () => {
    vi.spyOn(agentsAdminClient, "lookupOrigin").mockResolvedValue(
      { found: true, origin: "http://bard:29400", path: "/mcp", origin_id: "o1", group: { service_id: "s", name: "bard" } });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="address-0"]').setValue("http://bard:29400/mcp");
    await wrapper.get('[data-test="address-0"]').trigger("blur");
    await flushPromises();
    const name = wrapper.get('[data-test="name-0"]');
    expect((name.element as HTMLInputElement).value).toBe("bard");
    expect(name.attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("asks for a name when the address is new and sends addresses with an override token", async () => {
    vi.spyOn(agentsAdminClient, "lookupOrigin").mockResolvedValue(
      { found: false, origin: "http://bard:29400", path: "/mcp", origin_id: null, group: null });
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "bard" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="id"]').setValue("bard");
    await wrapper.get('[data-test="label"]').setValue("Bard");
    await wrapper.get('[data-test="address-0"]').setValue("http://bard:29400/mcp");
    await wrapper.get('[data-test="address-0"]').trigger("blur");
    await flushPromises();
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined(); // a new address needs a name
    await wrapper.get('[data-test="name-0"]').setValue("bard");
    await wrapper.get('[data-test="add-address"]').trigger("click");
    await wrapper.get('[data-test="address-1"]').setValue("http://bard2:29400/mcp");
    vi.mocked(agentsAdminClient.lookupOrigin).mockResolvedValue(
      { found: true, origin: "http://bard2:29400", path: "/mcp", origin_id: "o2", group: { service_id: "s", name: "bard" } });
    await wrapper.get('[data-test="address-1"]').trigger("blur");
    await flushPromises();
    await wrapper.get('[data-test="override-1"]').setValue("second");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="header-name"]').setValue("X-Test-Token");
    await wrapper.get('[data-test="header-value"]').setValue("parent");
    await submit(wrapper);
    expect(save).toHaveBeenCalledWith("bard", {
      label: "Bard", description: "", transport: "http",
      auth: { type: "header", header_name: "X-Test-Token", header_value: "parent" },
      addresses: [{ address: "http://bard:29400/mcp", name: "bard" }, { address: "http://bard2:29400/mcp", header_value: "second" }],
    });
    wrapper.unmount();
  });

  it("shows the origins of a catalog connection and keeps unretyped overrides", async () => {
    vi.spyOn(agentsAdminClient, "servers").mockResolvedValue({ bard: { label: "Bard", transport: "http", service_id: "s", path: "/mcp",
      auth: { type: "header", header_name: "X-Test-Token", has_value: true },
      origins: [{ origin_id: "o1", origin: "http://bard:29400", has_override: false }, { origin_id: "o2", origin: "http://bard2:29400", has_override: true }] } });
    const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "bard" });
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="row-bard"]').text()).toContain("http://bard:29400/mcp, http://bard2:29400/mcp");
    await edit(wrapper, "bard");
    await wrapper.get('[data-test="description"]').setValue("New description");
    expect((wrapper.get('[data-test="address-1"]').element as HTMLInputElement).value).toBe("http://bard2:29400/mcp");
    await submit(wrapper);
    expect(save.mock.calls[0][1].addresses).toEqual([{ address: "http://bard:29400/mcp" }, { address: "http://bard2:29400/mcp" }]);
    wrapper.unmount();
  });
});


it("keeps unresolved catalog origins visible and blocks saving until repaired", async () => {
  vi.mocked(agentsAdminClient.servers).mockResolvedValue({
    main: { label: "Armory", transport: "http", service_id: "group", path: "/mcp", origins: [{ origin_id: "missing" }] },
  });
  const wrapper = await mounted();
  expect(wrapper.get('[data-test="row-main"]').text()).toContain("Unavailable catalog address (missing)");
  await edit(wrapper, "main");
  expect(wrapper.get('[data-test="form"]').text()).toContain("Address missing is unavailable in Treasury");
  expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
  wrapper.unmount();
});


it("ignores a late lookup after the address changed twice", async () => {
  let finish!: (value: OriginLookup) => void;
  vi.spyOn(agentsAdminClient, "lookupOrigin").mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  const wrapper = await mounted();
  await wrapper.get('[data-test="add"]').trigger("click");
  const input = wrapper.get('[data-test="address-0"]');
  await input.setValue("http://service.example.test/mcp");
  await input.trigger("blur");
  await input.setValue("http://other.example.test/mcp");
  await input.setValue("http://service.example.test/mcp");
  finish({ found: true, origin: "http://service.example.test", path: "/mcp", origin_id: "old",
    group: { service_id: "old-group", name: "Stale name" } });
  await flushPromises();
  expect(wrapper.get<HTMLInputElement>('[data-test="name-0"]').element.value).toBe("");
  wrapper.unmount();
});

it("keeps stdio commands and arguments editable in the same drawer", async () => {
  vi.mocked(agentsAdminClient.servers).mockResolvedValue({
    main: { label: "Local tools", description: "Tools", transport: "stdio", command: "tools", args: ["--stdio"] },
  });
  const save = vi.spyOn(agentsAdminClient, "saveServer").mockResolvedValue({ saved: "main" });
  const wrapper = await mounted();
  expect(wrapper.get('[data-test="row-main"]').text()).toContain("tools --stdio");
  await edit(wrapper, "main");
  await wrapper.get('[data-test="description"]').setValue("Updated tools");
  await submit(wrapper);
  expect(save).toHaveBeenCalledWith("main", {
    label: "Local tools", description: "Updated tools", transport: "stdio", command: "tools", args: ["--stdio"],
  });
  wrapper.unmount();
});
