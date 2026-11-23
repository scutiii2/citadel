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

async function mounted(open = true) {
  const wrapper = mount(ToolServicesView, { attachTo: document.body });
  await flushPromises();
  if (open) await wrapper.get('button[aria-label="Open Bard"]').trigger("click");
  return { wrapper, card: open ? wrapper.get('[data-test="service-bard"]') : wrapper.get("main, section") };
}

/** The drawer's own save or discard question is the first ConfirmModal; the remove question is the last. */
async function confirmDrawer(wrapper: Awaited<ReturnType<typeof mounted>>["wrapper"]) {
  wrapper.findAllComponents(ConfirmModal)[0]!.vm.$emit("confirm");
  await flushPromises();
}

describe("ToolServicesView", () => {
  it("shows each service and leaves the saved token fields blank", async () => {
    const { wrapper } = await mounted(false);
    expect(wrapper.get('[data-test="row-bard"]').text()).toContain("Ready");
    expect(wrapper.get('[data-test="row-scribe"]').text()).toContain("Configure Scribe in Stronghold Admin.");
    expect(wrapper.get('[data-test="row-reader"]').text()).toContain("Reader is disabled in Stronghold Admin.");
    await wrapper.get('button[aria-label="Open Bard"]').trigger("click");
    const card = wrapper.get('[data-test="service-bard"]');
    expect(card.findAll("input[type=password]").map(({ element }) => (element as HTMLInputElement).value)).toEqual(["", ""]);
  });

  it("locks a known name and requires a name before saving a new address", async () => {
    const { wrapper, card } = await mounted();
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
    const save = () => wrapper.get('[data-test="save"]');
    expect(save().attributes("disabled")).toBeDefined();
    await card.get('[data-test="name-1"]').setValue("bard");
    expect(save().attributes("disabled")).toBeUndefined();
  });

  it("sends typed tokens, names for new addresses, and the draft enabled state", async () => {
    const save = vi.spyOn(toolServicesClient, "save").mockResolvedValue(bard);
    const { wrapper, card } = await mounted();
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
    await confirmDrawer(wrapper);
    expect(save).toHaveBeenCalledWith("bard", { enabled: false, token: "fake-parent", addresses: [
      { address }, { address: backup, name: "bard", header_value: "fake-backup" },
    ] });
  });

  it("omits a saved parent token and an unretyped override", async () => {
    const save = vi.spyOn(toolServicesClient, "save").mockResolvedValue(bard);
    const { wrapper, card } = await mounted();
    await card.get('input[role="switch"]').setValue(false);
    await card.trigger("submit");
    await confirmDrawer(wrapper);
    expect(save).toHaveBeenCalledWith("bard", { enabled: false, addresses: [{ address }] });
  });

  it("shows each origin's test result", async () => {
    const test = vi.spyOn(toolServicesClient, "test").mockResolvedValue({
      ok: false, message: "Some addresses are not ready.",
      origins: [{ origin_id: "o1", ok: true, message: "Ready." }, { origin_id: "o2", ok: false, message: "The token was refused." }],
    });
    const { wrapper, card } = await mounted();
    await wrapper.get('[data-test="test"]').trigger("click");
    await flushPromises();
    expect(test).toHaveBeenCalledWith("bard");
    expect(card.get('[data-test="test-result"]').text()).toContain("Ready.");
    expect(card.get('[data-test="test-result"]').text()).toContain("The token was refused.");
  });

  it("tests a service from its row without opening it", async () => {
    const test = vi.spyOn(toolServicesClient, "test").mockResolvedValue({ ok: true, message: "Every address is ready.", origins: [] });
    const { wrapper } = await mounted(false);
    await wrapper.get('[data-test="row-test-bard"]').trigger("click");
    await flushPromises();
    expect(test).toHaveBeenCalledWith("bard");
    expect(wrapper.get('[data-test="row-result-bard"]').attributes("aria-label")).toBe("Connected");
    expect(wrapper.get('[data-test="row-popover"]').text()).toContain("Every address is ready.");
    expect(wrapper.find('[data-test="service-bard"]').exists()).toBe(false);
  });

  it("keeps the draft after Treasury refuses a save", async () => {
    vi.spyOn(toolServicesClient, "save").mockRejectedValue(new Error(unavailable));
    const { wrapper, card } = await mounted();
    await card.get('input[role="switch"]').setValue(false);
    await card.trigger("submit");
    await confirmDrawer(wrapper);
    expect(card.get('[role="alert"]').text()).toBe(unavailable);
    expect(card.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(false);
    expect(card.get<HTMLInputElement>('[data-test="address-0"]').element.value).toBe(address);
  });

  it("asks for confirmation before clearing the connection", async () => {
    const clear = vi.spyOn(toolServicesClient, "clear").mockResolvedValue({ ...bard, origins: [], has_token: false });
    const { wrapper, card } = await mounted();
    await card.get('[data-test="clear"]').trigger("click");
    const dialog = wrapper.findAllComponents(ConfirmModal).at(-1)!;
    expect(dialog.props("open")).toBe(true);
    expect(clear).not.toHaveBeenCalled();
    dialog.vm.$emit("confirm");
    await flushPromises();
    expect(clear).toHaveBeenCalledWith("bard");
  });
});

it("keeps a draft when search hides its service, and discards after asking on Cancel", async () => {
  const { wrapper, card } = await mounted();
  await card.get('input[role="switch"]').setValue(false);
  await wrapper.get('[data-test="cancel"]').trigger("click");
  expect(wrapper.findAllComponents(ConfirmModal)[0]!.props("open")).toBe(true);
  await confirmDrawer(wrapper);
  expect(card.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(true);
});

describe("ToolServicesView row test result", () => {
  it("shows a cross with the error code of a failed test and what it means", async () => {
    vi.spyOn(toolServicesClient, "test").mockResolvedValue({ ok: false, code: "401", message: "Some addresses are not ready.",
      origins: [{ origin_id: "o1", ok: false, code: "401", message: "The token was refused." }] });
    const { wrapper } = await mounted(false);
    await wrapper.get('[data-test="row-test-bard"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-test="row-code"]').text()).toBe("401");
    expect(wrapper.get('[data-test="row-result-bard"]').attributes("aria-label")).toBe("Failed, code 401");
    expect(wrapper.get('[data-test="row-popover"]').text()).toContain("Some addresses are not ready.");
  });
});
