import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RangeSlider from "./RangeSlider.vue";

describe("RangeSlider", () => {
  it("places the handle from the value and keeps a native named input", () => {
    const wrapper = mount(RangeSlider, { props: { modelValue: 25, min: 0, max: 100 }, attrs: { "aria-label": "Length", class: "wide" } });
    expect(wrapper.attributes("style")).toContain("--v: 0.25");
    expect(wrapper.classes()).toContain("wide");
    const input = wrapper.get("input");
    expect(input.attributes("type")).toBe("range");
    expect(input.attributes("aria-label")).toBe("Length");
    expect(input.attributes("class")).toBeUndefined();
  });

  it("clamps a value outside the range and hides the stop dot near the end", () => {
    const high = mount(RangeSlider, { props: { modelValue: 500, min: 0, max: 100 } });
    expect(high.attributes("style")).toContain("--v: 1");
    expect(high.find(".stop").exists()).toBe(false);
    const low = mount(RangeSlider, { props: { modelValue: -3, min: 0, max: 100 } });
    expect(low.attributes("style")).toContain("--v: 0");
    expect(low.find(".stop").exists()).toBe(true);
  });

  it("emits a number for a number model and a string for a string model", async () => {
    const num = mount(RangeSlider, { props: { modelValue: 5, min: 0, max: 10 } });
    await num.get("input").setValue("7");
    expect(num.emitted("update:modelValue")).toEqual([[7]]);
    const str = mount(RangeSlider, { props: { modelValue: "5", min: 0, max: 10 } });
    await str.get("input").setValue("7");
    expect(str.emitted("update:modelValue")).toEqual([["7"]]);
  });
});
