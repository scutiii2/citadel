import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SegmentedControl from "./SegmentedControl.vue";

describe("SegmentedControl tabs", () => {
  it("links tabs to panels and navigates enabled options with arrows", async () => {
    const w = mount(SegmentedControl, { props: {
      modelValue: "first", mode: "tabs", idPrefix: "example", ariaLabel: "Modes",
      options: [{ value: "first", label: "First" }, { value: "disabled", label: "Unavailable", disabled: true }, { value: "last", label: "Last" }],
    } });
    expect(w.get('[role="tablist"]').attributes("aria-label")).toBe("Modes");
    const tabs = w.findAll('[role="tab"]');
    expect(tabs[0]!.attributes("aria-controls")).toBe("example-panel-first");
    expect(tabs[0]!.attributes("tabindex")).toBe("0");
    expect(tabs[2]!.attributes("tabindex")).toBe("-1");
    await tabs[0]!.trigger("keydown", { key: "ArrowRight" });
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["last"]);
    await tabs[0]!.trigger("keydown", { key: "Home" });
    expect(w.emitted("update:modelValue")!.at(-1)).toEqual(["first"]);
  });
});
