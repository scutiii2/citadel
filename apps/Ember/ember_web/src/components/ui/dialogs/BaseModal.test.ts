import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import BaseModal from "./BaseModal.vue";

const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

// jsdom does not fire `close` when a dialog is closed, as a browser does: do it here.
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});

describe("BaseModal", () => {
  it("does not echo a close the parent asked for", async () => {
    const wrapper = mount(BaseModal, { props: { open: true, title: "A" }, attachTo: document.body });
    await nextTick();

    await wrapper.setProps({ open: false });
    await nextTick();

    expect(wrapper.get("dialog").attributes("open")).toBeUndefined();
    expect(wrapper.emitted("close")).toBeUndefined();
    wrapper.unmount();
  });

  it("still reports a close the browser made while the parent wants it open", async () => {
    const wrapper = mount(BaseModal, { props: { open: true, title: "A" }, attachTo: document.body });
    await nextTick();

    wrapper.get("dialog").element.dispatchEvent(new Event("close"));

    expect(wrapper.emitted("close")).toHaveLength(1);
    wrapper.unmount();
  });

  it("asks the parent to close on the × button and on Escape", async () => {
    const wrapper = mount(BaseModal, { props: { open: true, title: "A" }, attachTo: document.body });
    await nextTick();

    await wrapper.get("button.close").trigger("click");
    await wrapper.get("dialog").trigger("cancel");

    expect(wrapper.emitted("close")).toHaveLength(2);
    wrapper.unmount();
  });
});
