import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DeleteButton from "./DeleteButton.vue";

describe("DeleteButton", () => {
  it("keeps its label in place and sets no inline size while busy (the CSS swaps it for a spinner)", async () => {
    const wrapper = mount(DeleteButton, { props: { label: "Delete", busy: false } });
    await wrapper.setProps({ busy: true });

    const button = wrapper.get("button");
    expect(button.attributes("aria-busy")).toBe("true");
    expect(wrapper.get(".label").text()).toBe("Delete");
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
