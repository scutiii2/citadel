import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http";
import { settingsClient } from "../../api/SettingsClient";
import SidebarPagesPanel from "./SidebarPagesPanel.vue";

vi.mock("../../api/SettingsClient", () => ({ settingsClient: { get: vi.fn(), set: vi.fn(), pages: vi.fn(), setPages: vi.fn() } }));

const client = vi.mocked(settingsClient);

async function panel(hidden: string[] = []) {
  client.pages.mockResolvedValue({ hidden });
  const wrapper = mount(SidebarPagesPanel);
  await flushPromises();
  return wrapper;
}

type Panel = Awaited<ReturnType<typeof panel>>;
const rows = (wrapper: Panel) => wrapper.findAll(".page-row");
const labels = (wrapper: Panel) => rows(wrapper).map((r) => r.get(".page-name").text());
const box = (wrapper: Panel, label: string) =>
  rows(wrapper).find((r) => r.get(".page-name").text() === label)!.get('input[type="checkbox"]');
const checked = (wrapper: Panel, label: string) => (box(wrapper, label).element as HTMLInputElement).checked;

beforeEach(() => {
  vi.clearAllMocks();
  client.setPages.mockImplementation(async (hidden) => ({ hidden }));
});

describe("SidebarPagesPanel", () => {
  it("lists the pages an admin may hide, not Chat or Settings", async () => {
    expect(labels(await panel())).toEqual(["Capabilities", "Agents", "Games", "Usage", "Tickets"]);
  });

  it("shows every page on by default and the stored hidden ones off", async () => {
    const wrapper = await panel(["/usage", "/games"]);

    expect(checked(wrapper, "Agents")).toBe(true);
    expect(checked(wrapper, "Usage")).toBe(false);
    expect(checked(wrapper, "Games")).toBe(false);
  });

  it("says the setting hides the page from the sidebar for every account", async () => {
    const text = (await panel()).text();

    expect(text).toContain("Applies to all accounts");
    expect(text).toContain("Show in the sidebar for everyone");
    expect(text).toContain("still open");
  });

  it("holds a flip as an unsaved change until Save", async () => {
    const wrapper = await panel();
    expect(wrapper.find(".save-bar").exists()).toBe(false);

    await box(wrapper, "Usage").setValue(false);

    expect(client.setPages).not.toHaveBeenCalled();
    expect(wrapper.get(".save-bar").text()).toContain("unsaved change");
    expect(wrapper.get(".save-bar").text()).toContain("every account");
  });

  it("saves the hidden ids on Save, then shows Saved", async () => {
    const wrapper = await panel();
    await box(wrapper, "Usage").setValue(false);
    await box(wrapper, "Games").setValue(false);

    await wrapper.get(".save-bar .primary").trigger("click");
    await flushPromises();

    expect(client.setPages).toHaveBeenCalledWith(["/games", "/usage"]);
    expect(wrapper.find(".save-bar").exists()).toBe(false);
    expect(wrapper.get(".chip.saved").text()).toBe("Saved");
  });

  it("drops the draft on Cancel without saving", async () => {
    const wrapper = await panel();
    await box(wrapper, "Usage").setValue(false);

    await wrapper.get(".save-bar button:not(.primary)").trigger("click");

    expect(client.setPages).not.toHaveBeenCalled();
    expect(checked(wrapper, "Usage")).toBe(true);
    expect(wrapper.find(".save-bar").exists()).toBe(false);
  });

  it("flipping back to the stored state clears the unsaved change", async () => {
    const wrapper = await panel();

    await box(wrapper, "Usage").setValue(false);
    await box(wrapper, "Usage").setValue(true);

    expect(wrapper.find(".save-bar").exists()).toBe(false);
  });

  it("offers Back to default only while something is hidden, and it makes an unsaved draft", async () => {
    const wrapper = await panel(["/usage"]);
    const reset = wrapper.findAll(".head button").find((b) => b.text() === "Back to default")!;

    await reset.trigger("click");

    expect(checked(wrapper, "Usage")).toBe(true);
    expect(client.setPages).not.toHaveBeenCalled();
    expect(wrapper.find(".save-bar").exists()).toBe(true);
    expect((await panel()).findAll(".head button").some((b) => b.text() === "Back to default")).toBe(false);
  });

  it("keeps ids it does not know when saving", async () => {
    const wrapper = await panel(["/future-page"]);
    await box(wrapper, "Usage").setValue(false);

    await wrapper.get(".save-bar .primary").trigger("click");
    await flushPromises();

    expect(client.setPages).toHaveBeenCalledWith(["/future-page", "/usage"]);
  });

  it("shows the error and keeps the draft when saving fails", async () => {
    const wrapper = await panel();
    client.setPages.mockRejectedValue(new ApiError(403, "Missing permission: settings.manage"));
    await box(wrapper, "Usage").setValue(false);

    await wrapper.get(".save-bar .primary").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Missing permission: settings.manage");
    expect(wrapper.find(".save-bar").exists()).toBe(true);
    expect(wrapper.find(".chip.saved").exists()).toBe(false);
  });

  it("shows a load error", async () => {
    client.pages.mockRejectedValue(new ApiError(500, "boom"));
    const wrapper = mount(SidebarPagesPanel);
    await flushPromises();

    expect(wrapper.text()).toContain("boom");
    expect(rows(wrapper)).toHaveLength(0);
  });
});
