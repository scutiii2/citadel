import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmPickCard from "./EmPickCard.vue";

describe("EmPickCard", () => {
  it("exposes selection and selects by click, Enter and Space", async () => {
    const wrapper = mount(EmPickCard, { props: { selected: true }, attrs: { "aria-label": "Guardian" }, slots: { default: "Card" } });
    expect(wrapper.attributes("role")).toBe("radio");
    expect(wrapper.attributes("aria-checked")).toBe("true");
    expect(wrapper.classes()).toContain("selected");
    await wrapper.trigger("click");
    await wrapper.trigger("keydown.enter");
    await wrapper.trigger("keydown.space");
    expect(wrapper.emitted("select")).toHaveLength(3);
  });

  it("blocks disabled selection for mouse and keyboard", async () => {
    const wrapper = mount(EmPickCard, { props: { selected: false, disabled: true } });
    expect(wrapper.attributes("aria-disabled")).toBe("true");
    expect(wrapper.attributes("tabindex")).toBe("-1");
    await wrapper.trigger("click");
    await wrapper.trigger("keydown.enter");
    await wrapper.trigger("keydown.space");
    expect(wrapper.emitted("select")).toBeUndefined();
  });
});
