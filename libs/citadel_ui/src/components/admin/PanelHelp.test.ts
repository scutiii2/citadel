import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PanelHelp from "./PanelHelp.vue";

const show = () => mount(PanelHelp, { props: { title: "Role roster" }, slots: { default: "What it is for." }, attachTo: document.body });

describe("PanelHelp", () => {
  it("opens a popover on click and closes it on a second click", async () => {
    const wrapper = show();
    const button = wrapper.get('[data-test="panel-help"]');
    expect(button.attributes("aria-label")).toBe("About Role roster");
    expect(document.body.textContent).not.toContain("What it is for.");
    await button.trigger("click");
    expect(button.attributes("aria-expanded")).toBe("true");
    expect(document.body.textContent).toContain("What it is for.");
    await button.trigger("click");
    expect(document.body.textContent).not.toContain("What it is for.");
    wrapper.unmount();
  });

  it("closes on Escape with focus back on the icon, and on a press outside", async () => {
    const wrapper = show();
    const button = wrapper.get('[data-test="panel-help"]');
    await button.trigger("click");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).not.toContain("What it is for.");
    expect(document.activeElement).toBe(button.element);
    await button.trigger("click");
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(document.body.textContent).not.toContain("What it is for.");
    wrapper.unmount();
  });
});
