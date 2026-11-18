import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ticketSettingsClient, type TicketSettings } from "../api/TicketSettingsClient";
import TicketSettingsView from "./TicketSettingsView.vue";

const SETTINGS: TicketSettings = {
  tags: { email: "Mail problems", other: "Anything else" },
  auto_hourly_cap: 5,
  recent_hours: 24,
  elevation: { high: { tickets: 3, recent: 2 } },
  laya: { min_confidence: 0.7, candidates: 5, timeout_seconds: 20 },
};

beforeEach(() => {
  vi.spyOn(ticketSettingsClient, "get").mockResolvedValue(SETTINGS);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(TicketSettingsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}

describe("TicketSettingsView", () => {
  it("shows the saved tags and limits", async () => {
    const wrapper = await mounted();
    const names = wrapper.findAll('[data-test="tag-name"]').map((input) => (input.element as HTMLInputElement).value);
    expect(names).toEqual(["email", "other"]);
    expect((wrapper.get('[data-test="cap"]').element as HTMLInputElement).value).toBe("5");
    wrapper.unmount();
  });

  it("adds a tag and saves the whole editable document", async () => {
    const save = vi.spyOn(ticketSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await wrapper.get('[data-test="tag-add"]').trigger("click");
    const rows = wrapper.findAll('[data-test="tag"]');
    await rows[2].get('[data-test="tag-name"]').setValue(" Billing ");
    await rows[2].get('[data-test="tag-description"]').setValue("Payments");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({
      tags: { email: "Mail problems", other: "Anything else", billing: "Payments" },
      auto_hourly_cap: 5,
      recent_hours: 24,
      laya: { min_confidence: 0.7, candidates: 5, timeout_seconds: 20 },
    });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next ticket");
    wrapper.unmount();
  });

  it("blocks a blank or repeated tag and keeps two tags", async () => {
    const wrapper = await mounted();
    await wrapper.get('[data-test="tag-add"]').trigger("click");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-test="problem"]').text()).toContain("name and a description");
    await wrapper.findAll('[data-test="tag"]')[2].get('[data-test="tag-name"]').setValue("EMAIL");
    await wrapper.findAll('[data-test="tag"]')[2].get('[data-test="tag-description"]').setValue("x");
    expect(wrapper.get('[data-test="problem"]').text()).toContain("different");
    await wrapper.findAll('[data-test="tag-remove"]')[2].trigger("click");
    expect(wrapper.findAll('[data-test="tag-remove"]')[0].attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("shows the refusal of the server", async () => {
    vi.spyOn(ticketSettingsClient, "save").mockRejectedValue(new Error("laya.candidates must be at most 10."));
    const wrapper = await mounted();
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("at most 10");
    wrapper.unmount();
  });
});
