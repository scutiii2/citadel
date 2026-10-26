import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ListRow from "./ListRow.vue";

describe("ListRow", () => {
  it("is a button that marks the active row", () => {
    const row = mount(ListRow, { props: { active: true }, slots: { default: "Row" } });
    expect(row.element.tagName).toBe("BUTTON");
    expect(row.classes()).toContain("active");
    expect(row.attributes("aria-current")).toBe("true");
  });

  it("has no aria-current when inactive and passes disabled and clicks through", async () => {
    const row = mount(ListRow, { attrs: { disabled: true } });
    expect(row.attributes("aria-current")).toBeUndefined();
    expect(row.attributes("disabled")).toBeDefined();
  });
});
