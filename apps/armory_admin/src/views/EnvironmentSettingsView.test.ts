import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { environmentClient, type EnvironmentSetting } from "../api/EnvironmentClient";
import EnvironmentSettingsView from "./EnvironmentSettingsView.vue";

const SETTINGS: EnvironmentSetting[] = [
  { field: "stronghold_url", label: "Stronghold address", group: "Services", kind: "url", help: "", secret: false, restart: false, stored: true, value: "http://127.0.0.1:29650" },
  { field: "laya_url", label: "Laya address", group: "Tickets", kind: "url", help: "", secret: false, restart: true, stored: false, value: "" },
  { field: "media_signing_key", label: "Video link signing key", group: "Links", kind: "text", help: "", secret: true, restart: true, stored: true, has_value: true },
  { field: "obsidian_allow_write", label: "Allow writes", group: "Obsidian", kind: "bool", help: "", secret: false, restart: false, stored: false, value: false },
  { field: "obsidian_timeout", label: "Timeout", group: "Obsidian", kind: "number", help: "", secret: false, restart: false, stored: false, value: 5 },
];

beforeEach(() => {
  vi.spyOn(environmentClient, "get").mockResolvedValue({ settings: SETTINGS });
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(EnvironmentSettingsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const input = (wrapper: Awaited<ReturnType<typeof mounted>>, field: string) => wrapper.get(`[data-test="row-${field}"] [data-test="input"]`);

describe("EnvironmentSettingsView", () => {
  it("shows the values, hides a secret and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((input(wrapper, "stronghold_url").element as HTMLInputElement).value).toBe("http://127.0.0.1:29650");
    expect((input(wrapper, "media_signing_key").element as HTMLInputElement).value).toBe("");
    expect(wrapper.html()).not.toContain("s3cret");
    expect(wrapper.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("sends only what changed, with numbers as numbers and a secret as typed", async () => {
    const save = vi.spyOn(environmentClient, "save").mockResolvedValue({ settings: SETTINGS, restart: ["media_signing_key"] });
    const wrapper = await mounted();
    await input(wrapper, "stronghold_url").setValue("http://stronghold:29650");
    await input(wrapper, "obsidian_timeout").setValue("12");
    await input(wrapper, "obsidian_allow_write").setValue(true);
    await input(wrapper, "media_signing_key").setValue("new-key");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({
      stronghold_url: "http://stronghold:29650", obsidian_timeout: 12, obsidian_allow_write: true, media_signing_key: "new-key",
    });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("Used after Armory restarts: Video link signing key");
    wrapper.unmount();
  });

  it("puts a saved value back to the default with null", async () => {
    const save = vi.spyOn(environmentClient, "save").mockResolvedValue({ settings: SETTINGS });
    const wrapper = await mounted();
    await wrapper.get('[data-test="row-stronghold_url"] [data-test="reset"]').trigger("click");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ stronghold_url: null });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("uses it now");
    wrapper.unmount();
  });

  it("shows the refusal and keeps what was typed", async () => {
    vi.spyOn(environmentClient, "save").mockRejectedValue(new Error("Stronghold address: use an http(s) address without a login."));
    const wrapper = await mounted();
    await input(wrapper, "stronghold_url").setValue("ftp://x");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("http(s) address");
    expect((input(wrapper, "stronghold_url").element as HTMLInputElement).value).toBe("ftp://x");
    wrapper.unmount();
  });
});
