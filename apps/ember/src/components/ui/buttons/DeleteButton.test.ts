import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DeleteButton from "./DeleteButton.vue";

describe("DeleteButton", () => {
  it("is not pinned or collapsed when busy flips while it is hidden (a closed dialog)", async () => {
    // jsdom has no layout, so offsetWidth is 0 like a button inside a closed dialog.
    const wrapper = mount(DeleteButton, { props: { label: "Delete", busy: false } });
    await wrapper.setProps({ busy: true });
    await wrapper.setProps({ busy: false });

    const button = wrapper.get("button");
    expect(button.classes()).not.toContain("collapsed");
    expect((button.element as HTMLButtonElement).style.width).toBe("");
  });

  it("emits click once, and ignores a click while busy", async () => {
    const wrapper = mount(DeleteButton, { props: { label: "Delete" } });
    await wrapper.get("button").trigger("click");
    await wrapper.setProps({ busy: true });
    await wrapper.get("button").trigger("click");

    expect(wrapper.emitted("click")).toHaveLength(1);
  });
});
