import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import ForgeFolderField from "./ForgeFolderField.vue";

const setup = (props: object = {}) =>
  mount(ForgeFolderField, { props: { label: "Folder", modelValue: "C:/site", browse: null, ...props } });
const browseButton = (wrapper: ReturnType<typeof setup>) => wrapper.get("button.browse");

describe("ForgeFolderField", () => {
  it("fills the field with the folder picked on the worker's computer", async () => {
    const browse = vi.fn().mockResolvedValue("D:/work/site");
    const wrapper = setup({ browse, "onUpdate:modelValue": (v: string) => wrapper.setProps({ modelValue: v }) });

    await browseButton(wrapper).trigger("click");
    await flushPromises();

    expect(browse).toHaveBeenCalledWith("C:/site");
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("D:/work/site");
  });

  it("keeps the typed path when the dialog is cancelled", async () => {
    const wrapper = setup({ browse: vi.fn().mockResolvedValue(null) });

    await browseButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("C:/site");
  });

  it("says that a dialog is open while it waits, and does not open a second one", async () => {
    let finish: (path: string | null) => void = () => {};
    const browse = vi.fn(() => new Promise<string | null>((resolve) => (finish = resolve)));
    const wrapper = setup({ browse });

    await browseButton(wrapper).trigger("click");
    expect(wrapper.text()).toContain("A folder dialog is open on that worker's computer.");
    expect(browseButton(wrapper).text()).toBe("Waiting…");
    expect((browseButton(wrapper).element as HTMLButtonElement).disabled).toBe(true);
    finish(null);
    await flushPromises();

    expect(browse).toHaveBeenCalledTimes(1);
    expect(browseButton(wrapper).text()).toBe("Browse…");
  });

  it("shows why it failed and keeps the typed path", async () => {
    const wrapper = setup({ browse: vi.fn().mockRejectedValue(new Error("That worker is offline")) });

    await browseButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toBe("That worker is offline");
    expect((wrapper.get("input").element as HTMLInputElement).value).toBe("C:/site");
  });

  it("disables Browse with the reason when it cannot be used", () => {
    const wrapper = setup({ browse: null, unavailable: "That worker is offline. Type the path instead." });

    expect((browseButton(wrapper).element as HTMLButtonElement).disabled).toBe(true);
    expect(browseButton(wrapper).attributes("title")).toContain("offline");
    expect(wrapper.text()).toContain("Type the path instead.");
  });
});
