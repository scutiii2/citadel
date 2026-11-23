import { flushPromises, mount } from "@vue/test-utils";
import { beforeAll, expect, it } from "vitest";
import RecordDrawer from "./RecordDrawer.vue";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});

it("keeps the same body and draft across resize and confirms dismissal once", async () => {
  const wrapper = mount(RecordDrawer, { props: { open: true, title: "Agent details", editing: true },
    slots: { default: '<input aria-label="Agent name" />', footer: "<button>Save</button>" } });
  await flushPromises();
  const body = wrapper.get(".drawer-body").element;
  const input = wrapper.get<HTMLInputElement>("input");
  await input.setValue("Draft");
  await wrapper.get('[aria-label="Expand drawer"]').trigger("click");
  expect(wrapper.get(".record-drawer").classes()).toContain("expanded");
  await wrapper.get('[aria-label="Restore drawer size"]').trigger("click");
  expect(wrapper.get(".drawer-body").element).toBe(body);
  expect(wrapper.get("input").element).toBe(input.element);
  expect(input.element.value).toBe("Draft");
  await wrapper.get(".record-drawer").trigger("cancel");
  expect(wrapper.emitted("close")).toBeUndefined();
  await wrapper.get('dialog[aria-label="Discard changes?"][open] .cancel').trigger("click");
  expect(input.element.value).toBe("Draft");
  await wrapper.get('.record-drawer [aria-label="Close"]').trigger("click");
  await wrapper.get('dialog[aria-label="Discard changes?"][open] .confirm').trigger("click");
  expect(wrapper.emitted("close")).toHaveLength(1);
  wrapper.unmount();
});
