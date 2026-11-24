import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SearchField from "./SearchField.vue";

describe("SearchField", () => {
  it("binds the text, labels the input and forwards attributes to it", async () => {
    const field = mount(SearchField, { props: { modelValue: "", label: "Search things", "onUpdate:modelValue": (v: string) => field.setProps({ modelValue: v }) }, attrs: { placeholder: "Find…", class: "mine" } });
    const input = field.get("input[type=search]");
    expect(input.attributes("aria-label")).toBe("Search things");
    expect(input.attributes("placeholder")).toBe("Find…");
    expect(field.classes()).toContain("mine");
    await input.setValue("abc");
    expect(field.props("modelValue")).toBe("abc");
  });

  it("renders the trailing slot", () => {
    const field = mount(SearchField, { props: { modelValue: "", label: "x" }, slots: { default: "<button>Go</button>" } });
    expect(field.get("button").text()).toBe("Go");
  });
});
