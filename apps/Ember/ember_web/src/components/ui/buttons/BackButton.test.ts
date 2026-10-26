import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BackButton from "./BackButton.vue";

describe("BackButton", () => {
  it("is a button with an arrow and the label, and passes clicks and disabled through", async () => {
    let clicks = 0;
    const w = mount(BackButton, { slots: { default: "All notes" }, attrs: { onClick: () => clicks++ } });
    expect(w.element.tagName).toBe("BUTTON");
    expect(w.text()).toBe("‹ All notes");
    expect(w.classes()).toContain("chip");
    await w.trigger("click");
    expect(clicks).toBe(1);
    expect(mount(BackButton, { attrs: { disabled: true } }).attributes("disabled")).toBeDefined();
  });

  it("can be a ghost instead of a chip", () => {
    const w = mount(BackButton, { props: { ghost: true } });
    expect(w.classes()).toContain("ghost");
    expect(w.classes()).not.toContain("chip");
  });
});
