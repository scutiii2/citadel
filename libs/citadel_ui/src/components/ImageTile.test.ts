import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import ImageTile from "./ImageTile.vue";

beforeEach(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

const tile = (props: Partial<{ src: string; name: string; busy: boolean }> = {}) =>
  mount(ImageTile, { props: { src: "blob:1", name: "photo.png", ...props }, attachTo: document.body });

describe("ImageTile", () => {
  it("shows the picture and asks to be removed", async () => {
    const wrapper = tile();

    expect(wrapper.get("img").attributes()).toMatchObject({ src: "blob:1", alt: "photo.png" });
    await wrapper.get('button[aria-label="Remove photo.png"]').trigger("click");
    expect(wrapper.emitted("remove")).toHaveLength(1);
    wrapper.unmount();
  });

  it("enlarges the picture on a click", async () => {
    const wrapper = tile();

    await wrapper.get('button[aria-label="Enlarge photo.png"]').trigger("click");
    await flushPromises();

    expect(wrapper.find("dialog[open] img").attributes("src")).toBe("blob:1");
    wrapper.unmount();
  });

  it("shows the name when there is no picture to show, and stays removable", async () => {
    const wrapper = tile();

    await wrapper.get("img").trigger("error");

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.text()).toContain("photo.png");
    expect(wrapper.find('button[aria-label="Remove photo.png"]').exists()).toBe(true);
    expect(tile({ src: "" }).find("img").exists()).toBe(false);
    wrapper.unmount();
  });

  it("says it is busy while the file is still being read", () => {
    expect(tile({ busy: true }).get(".image-tile").attributes("aria-busy")).toBe("true");
  });
});
