import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { settingsClient } from "../../api/SettingsClient";
import CalendarChannelsPanel from "./CalendarChannelsPanel.vue";

vi.mock("../../api/SettingsClient", () => ({ settingsClient: { get: vi.fn(), set: vi.fn() } }));
const client = vi.mocked(settingsClient);
const ALL_ON = { force_tool_approval: false, calendar_inapp: true, calendar_email: true, calendar_push: true };

beforeEach(() => {
  vi.clearAllMocks();
  client.get.mockResolvedValue(ALL_ON);
});

describe("CalendarChannelsPanel", () => {
  it("shows the three channels as stored and keeps Save disabled until something changes", async () => {
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    const switches = wrapper.findAll<HTMLInputElement>("input[role=switch]");
    expect(switches.map((s) => s.element.checked)).toEqual([true, true, true]);
    expect(wrapper.get("button.save").attributes("disabled")).toBeDefined();
  });

  it("saves only the channels that changed, one request each, after Save", async () => {
    client.set.mockResolvedValue({});
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    await wrapper.findAll("input[role=switch]")[2]!.setValue(false);
    expect(client.set).not.toHaveBeenCalled();
    await wrapper.get("button.save").trigger("click");
    await flushPromises();
    expect(client.set.mock.calls).toEqual([["calendar_push", false]]);
  });

  it("drops the draft on Cancel", async () => {
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    await wrapper.findAll("input[role=switch]")[0]!.setValue(false);
    await wrapper.get("button.cancel").trigger("click");
    expect(wrapper.findAll<HTMLInputElement>("input[role=switch]")[0]!.element.checked).toBe(true);
  });

  it("keeps the draft and shows the error when saving fails", async () => {
    client.set.mockRejectedValue(new Error("nope"));
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    await wrapper.findAll("input[role=switch]")[1]!.setValue(false);
    await wrapper.get("button.save").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("nope");
    expect(wrapper.findAll<HTMLInputElement>("input[role=switch]")[1]!.element.checked).toBe(false);
  });
});
