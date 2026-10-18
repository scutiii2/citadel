import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import ForgeNewGroupModal from "./ForgeNewGroupModal.vue";

const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});

const setup = (props: object = {}) => mount(ForgeNewGroupModal, { props: { open: true, busy: false, error: "", ...props }, attachTo: document.body });

describe("ForgeNewGroupModal", () => {
  it("creates a group with a title and the chosen starting mode", async () => {
    const wrapper = setup();

    await wrapper.get("input[type=text]").setValue("  Build the site ");
    await wrapper.findAll("button").find((b) => b.text() === "Plan")!.trigger("click");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("create")).toEqual([["Build the site", "plan"]]);
  });

  it("starts in Ask and never offers full auto", () => {
    const wrapper = setup();

    expect(wrapper.findAll("button").map((b) => b.text())).not.toContain("Full auto");
  });

  it("needs a title", async () => {
    const wrapper = setup();

    expect((wrapper.get("button[type=submit]").element as HTMLButtonElement).disabled).toBe(true);
    await wrapper.get("input[type=text]").setValue("   ");
    expect((wrapper.get("button[type=submit]").element as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows an error and forgets the draft when reopened", async () => {
    const wrapper = setup({ error: "At most 50 groups per account - delete some first" });
    expect(wrapper.get("[role=alert]").text()).toContain("At most 50");

    await wrapper.get("input[type=text]").setValue("Old");
    await wrapper.setProps({ open: false });
    await wrapper.setProps({ open: true });
    expect((wrapper.get("input[type=text]").element as HTMLInputElement).value).toBe("");
  });
});
