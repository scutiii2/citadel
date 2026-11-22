import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { toolServicesClient, type ToolService } from "../api/ToolServicesClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PasswordInput from "../components/PasswordInput.vue";
import ToolServicesView from "./ToolServicesView.vue";

const address = "http://bard:29400";
const backup = "http://bard2:29400";
const unavailable = "[1002] Treasury is unavailable. Nothing was saved.";
const bard: ToolService = {
  name: "bard", label: "Bard", enabled: true, service_id: "s", has_token: true,
  origins: [{ origin_id: "o1", origin: address, has_override: true }],
  ready: true, reason: null,
};
const services: ToolService[] = [
  bard,
  { name: "scribe", label: "Scribe", enabled: true, service_id: null, has_token: false,
    origins: [], ready: false, reason: "Configure Scribe in Stronghold Admin." },
  { name: "reader", label: "Reader", enabled: false, service_id: null, has_token: false,
    origins: [], ready: false, reason: "Reader is disabled in Stronghold Admin." },
];

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
});

beforeEach(() => {
  vi.spyOn(toolServicesClient, "list").mockResolvedValue(services);
  vi.spyOn(toolServicesClient, "lookup").mockImplementation(async (value) => value === address
    ? { found: true, origin: address, path: "", origin_id: "o1", group: { service_id: "s", name: "bard" } }
    : { found: false, origin: value, path: "", origin_id: null, group: null });
});

enableAutoUnmount(afterEach);
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(ToolServicesView, { attachTo: document.body });
  await flushPromises();
  return { wrapper, card: wrapper.get('[data-test="service-bard"]') };
}

describe("ToolServicesView", () => {
  it("shows each service and leaves the saved token fields blank", async () => {
    const { wrapper, card } = await mounted();
    expect(card.text()).toContain("Ready");
    expect(wrapper.get('[data-test="service-scribe"]').text()).toContain("Configure Scribe in Stronghold Admin.");
    expect(wrapper.get('[data-test="service-reader"]').text()).toContain("Reader is disabled in Stronghold Admin.");
    expect(card.findAll("input[type=password]").map(({ element }) => (element as HTMLInputElement).value)).toEqual(["", ""]);
  });

  it("locks a known name and requires a name before saving a new address", async () => {
    const { card } = await mounted();
    await card.get('[data-test="address-0"]').trigger("blur");
    await flushPromises();
    const known = card.get<HTMLInputElement>('[data-test="name-0"]');
    expect(known.element.value).toBe("bard");
    expect(known.element.disabled || known.element.readOnly).toBe(true);
    await card.get('[data-test="add-address"]').trigger("click");
    const field = card.get('[data-test="address-1"]');
    await field.setValue(backup);
    await field.trigger("blur");
    await flushPromises();
    expect(card.get('[data-test="save"]').attributes("disabled")).toBeDefined();
    await card.get('[data-test="name-1"]').setValue("bard");
    expect(card.get('[data-test="save"]').attributes("disabled")).toBeUndefined();
  });

  it("sends typed tokens, names for new addresses, and the draft enabled state", async () => {
    const save = vi.spyOn(toolServicesClient, "save").mockResolvedValue(bard);
    const { card } = await mounted();
    await card.get('[data-test="add-address"]').trigger("click");
    const field = card.get('[data-test="address-1"]');
    await field.setValue(backup);
    await field.trigger("blur");
    await flushPromises();
    await card.get('[data-test="name-1"]').setValue("bard");
    const passwords = card.findAllComponents(PasswordInput);
    passwords[0].vm.$emit("update:modelValue", "fake-parent");
    passwords[2].vm.$emit("update:modelValue", "fake-backup");
    await card.get('input[role="switch"]').setValue(false);
    await card.trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("bard", { enabled: false, token: "fake-parent", addresses: [
      { address }, { address: backup, name: "bard", header_value: "fake-backup" },
    ] });
  });

  it("omits a saved parent token and an unretyped override", async () => {
    const save = vi.spyOn(toolServicesClient, "save").mockResolvedValue(bard);
    const { card } = await mounted();
    await card.trigger("submit");
    expect(save).toHaveBeenCalledWith("bard", { enabled: true, addresses: [{ address }] });
  });

  it("shows each origin's test result", async () => {
    const test = vi.spyOn(toolServicesClient, "test").mockResolvedValue({
      ok: false, message: "Some addresses are not ready.",
      origins: [{ origin_id: "o1", ok: true, message: "Ready." }, { origin_id: "o2", ok: false, message: "The token was refused." }],
    });
    const { card } = await mounted();
    await card.get('[data-test="test"]').trigger("click");
    await flushPromises();
    expect(test).toHaveBeenCalledWith("bard");
    expect(card.get('[data-test="test-result"]').text()).toContain("Ready.");
    expect(card.get('[data-test="test-result"]').text()).toContain("The token was refused.");
  });

  it("keeps the draft after Treasury refuses a save", async () => {
    vi.spyOn(toolServicesClient, "save").mockRejectedValue(new Error(unavailable));
    const { card } = await mounted();
    await card.get('input[role="switch"]').setValue(false);
    await card.trigger("submit");
    await flushPromises();
    expect(card.get('[role="alert"]').text()).toBe(unavailable);
    expect(card.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(false);
    expect(card.get<HTMLInputElement>('[data-test="address-0"]').element.value).toBe(address);
  });

  it("asks for confirmation before clearing the connection", async () => {
    const clear = vi.spyOn(toolServicesClient, "clear").mockResolvedValue({ ...bard, origins: [], has_token: false });
    const { wrapper, card } = await mounted();
    await card.get('[data-test="clear"]').trigger("click");
    const dialog = wrapper.getComponent(ConfirmModal);
    expect(dialog.props("open")).toBe(true);
    expect(clear).not.toHaveBeenCalled();
    dialog.vm.$emit("confirm");
    await flushPromises();
    expect(clear).toHaveBeenCalledWith("bard");
  });
});
