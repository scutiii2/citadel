import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
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

  it("contains independent actions in the selected frame without nesting buttons", async () => {
    const select = vi.fn();
    const row = mount(ListRow, {
      props: { active: true }, attrs: { "aria-label": "Edit skill", onClick: select },
      slots: { default: "Skill", actions: "<button>Approve</button>" },
    });
    expect(row.element.tagName).toBe("DIV");
    expect(row.classes()).toContain("active");
    expect(row.find("button button").exists()).toBe(false);
    expect(row.get('button[aria-label="Edit skill"]').attributes("aria-current")).toBe("true");
    await row.findAll("button")[1]!.trigger("click");
    expect(select).not.toHaveBeenCalled();
    await row.get('button[aria-label="Edit skill"]').trigger("click");
    expect(select).toHaveBeenCalledTimes(1);
  });
});
