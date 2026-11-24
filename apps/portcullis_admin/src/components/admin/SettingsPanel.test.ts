import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http";
import { settingsClient } from "../../api/SettingsClient";
import ConfirmModal from "./ConfirmModal.vue";
import SettingsPanel from "./SettingsPanel.vue";

vi.mock("../../api/SettingsClient", () => ({ settingsClient: { get: vi.fn(), set: vi.fn() } }));

const client = vi.mocked(settingsClient);

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
});

async function panel(forced: boolean) {
  client.get.mockResolvedValue({ force_tool_approval: forced });
  const wrapper = mount(SettingsPanel, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
type Panel = Awaited<ReturnType<typeof panel>>;

const box = (wrapper: Panel) => wrapper.get('input[type="checkbox"]');
const isOn = (wrapper: Panel) => (box(wrapper).element as HTMLInputElement).checked;
const save = (wrapper: Panel) => wrapper.get('[data-test="save"]');
const cancelIcon = (wrapper: Panel) => wrapper.get('[data-test="cancel"]');
const discard = (wrapper: Panel) => wrapper.getComponent(ConfirmModal);

beforeEach(() => {
  vi.clearAllMocks();
  client.set.mockResolvedValue({ force_tool_approval: true });
});
afterEach(() => { document.body.innerHTML = ""; });

describe("SettingsPanel", () => {
  it("shows whether approval is required and explains the switch", async () => {
    expect(isOn(await panel(true))).toBe(true);
    const off = await panel(false);
    expect(isOn(off)).toBe(false);
    expect(off.text()).toContain("Require approval for every tool");
    expect(off.text()).toContain("Applies to all users");
    await off.get('[data-test="panel-help"]').trigger("click");
    expect(document.body.textContent).toContain("Allow for this chat");
  });

  it("reserves both icon slots and shows Cancel × then Save only while dirty", async () => {
    const wrapper = await panel(false);
    const slots = wrapper.findAll(".draft-actions .action-slot");
    expect(slots).toHaveLength(2);
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    await box(wrapper).setValue(true);
    expect(cancelIcon(wrapper).element.parentElement).toBe(slots[0]!.element);
    expect(save(wrapper).element.parentElement).toBe(slots[1]!.element);
    expect(cancelIcon(wrapper).attributes("aria-label")).toBe("Cancel tool approval changes");
    expect(wrapper.get(".unsaved").text()).toContain("on applies to every user");
    expect(client.set).not.toHaveBeenCalled();
  });

  it("saves the draft, then shows Saved", async () => {
    const wrapper = await panel(false);
    await box(wrapper).setValue(true);
    await save(wrapper).trigger("click");
    await flushPromises();
    expect(client.set).toHaveBeenCalledWith("force_tool_approval", true);
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    expect(wrapper.get(".action-message.ok").text()).toBe("Saved");
    expect(isOn(wrapper)).toBe(true);
  });

  it("turns it off again", async () => {
    const wrapper = await panel(true);
    await box(wrapper).setValue(false);
    await save(wrapper).trigger("click");
    await flushPromises();
    expect(client.set).toHaveBeenCalledWith("force_tool_approval", false);
  });

  it("confirms before discarding, keeps the draft when dismissed, and restores the saved value when confirmed", async () => {
    const wrapper = await panel(false);
    await box(wrapper).setValue(true);
    await cancelIcon(wrapper).trigger("click");
    expect(discard(wrapper).props("open")).toBe(true);
    await discard(wrapper).vm.$emit("close");
    expect(isOn(wrapper)).toBe(true);
    await cancelIcon(wrapper).trigger("click");
    await discard(wrapper).vm.$emit("confirm");
    await flushPromises();
    expect(client.set).not.toHaveBeenCalled();
    expect(isOn(wrapper)).toBe(false);
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
  });

  it("returns focus to search once the icons disappear after discarding", async () => {
    const wrapper = await panel(false);
    await box(wrapper).setValue(true);
    await cancelIcon(wrapper).trigger("click");
    await discard(wrapper).vm.$emit("confirm");
    await flushPromises();
    expect(document.activeElement).toBe(wrapper.get('input[type="search"]').element);
  });

  it("flipping back to the stored value clears the unsaved change", async () => {
    const wrapper = await panel(false);
    await box(wrapper).setValue(true);
    await box(wrapper).setValue(false);
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
  });

  it("shows the error next to the panel and keeps the draft when saving fails", async () => {
    const wrapper = await panel(false);
    client.set.mockRejectedValue(new ApiError(403, "Missing permission: roles.manage"));
    await box(wrapper).setValue(true);
    await save(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.get(".error").text()).toContain("Missing permission: roles.manage");
    expect(wrapper.find('[data-test="save"]').exists()).toBe(true);
    expect(wrapper.find(".action-message.ok").exists()).toBe(false);
  });

  it("keeps the draft while search hides the setting", async () => {
    const wrapper = await panel(false);
    await box(wrapper).setValue(true);
    await wrapper.get('input[type="search"]').setValue("zzz");
    expect(wrapper.text()).toContain("No settings match your search.");
    expect(wrapper.get(".body").attributes("style")).toContain("display: none");
    await wrapper.get('input[type="search"]').setValue("");
    expect(isOn(wrapper)).toBe(true);
    expect(wrapper.find('[data-test="save"]').exists()).toBe(true);
  });

  it("tells its page whether the stored value differs from the default", async () => {
    const off = await panel(false);
    const on = await panel(true);
    expect(off.emitted("modified")?.at(-1)).toEqual([false]);
    expect(on.emitted("modified")?.at(-1)).toEqual([true]);
    expect(on.find(".dot").exists()).toBe(true);
    expect(off.find(".dot").exists()).toBe(false);
  });

  it("offers Back to default only while the switch is on, and it makes an unsaved draft", async () => {
    const wrapper = await panel(true);
    const reset = () => wrapper.findAll("button").find((b) => b.text() === "Back to default");
    await reset()!.trigger("click");
    expect(client.set).not.toHaveBeenCalled();
    expect(isOn(wrapper)).toBe(false);
    expect(wrapper.get(".unsaved").text()).toContain("off applies to every user");
    expect(reset()).toBeUndefined();
    await save(wrapper).trigger("click");
    await flushPromises();
    expect(client.set).toHaveBeenCalledWith("force_tool_approval", false);
    expect(wrapper.emitted("modified")?.at(-1)).toEqual([false]);
  });

  it("has no Back to default when the switch is already off", async () => {
    expect((await panel(false)).findAll("button").some((b) => b.text() === "Back to default")).toBe(false);
  });

  it("shows an error when the setting cannot be read", async () => {
    client.get.mockRejectedValue(new ApiError(500, "boom"));
    const wrapper = mount(SettingsPanel);
    await flushPromises();
    expect(wrapper.text()).toContain("boom");
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false);
  });
});
