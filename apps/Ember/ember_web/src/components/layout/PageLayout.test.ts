import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PageLayout from "./PageLayout.vue";

describe("PageLayout", () => {
  it("renders the page title and description in its header", () => {
    const wrapper = mount(PageLayout, { props: { title: "Notes", description: "Your private notes." } });
    expect(wrapper.get("header h2.page-title").text()).toBe("Notes");
    expect(wrapper.get("header .page-description").text()).toBe("Your private notes.");
    expect(wrapper.element.tagName).toBe("SECTION");
    expect(wrapper.classes()).toEqual(expect.arrayContaining(["page", "info-page"]));
  });

  it("omits an absent description and empty optional rows", () => {
    const wrapper = mount(PageLayout, { props: { title: "Notes" } });
    expect(wrapper.find(".page-description").exists()).toBe(false);
    expect(wrapper.find(".page-actions").exists()).toBe(false);
    expect(wrapper.find(".page-toolbar").exists()).toBe(false);
  });

  it("places actions in the header", () => {
    const wrapper = mount(PageLayout, { props: { title: "Notes" }, slots: { actions: "<button>New note</button>" } });
    expect(wrapper.get("header .page-actions button").text()).toBe("New note");
  });

  it("places the toolbar after the header and before the body", () => {
    const wrapper = mount(PageLayout, { props: { title: "Notes" }, slots: { toolbar: '<input aria-label="Search notes" />', default: '<article>Saved notes</article>' } });
    expect(wrapper.get(".page-toolbar input").attributes("aria-label")).toBe("Search notes");
    expect(Array.from(wrapper.get(".page-column").element.children).map(element => element.tagName)).toEqual(["HEADER", "DIV", "ARTICLE"]);
  });

  it("renders page content in the default slot", () => {
    const wrapper = mount(PageLayout, { props: { title: "Notes" }, slots: { default: "<article>A saved note</article>" } });
    expect(wrapper.get(".page-column > article").text()).toBe("A saved note");
  });

  it("supports a full-width column and returns to the default width", async () => {
    const wrapper = mount(PageLayout, { props: { title: "Tickets", wide: true } });
    expect(wrapper.get(".page-column").classes()).toContain("page-column-wide");
    await wrapper.setProps({ wide: false });
    expect(wrapper.get(".page-column").classes()).not.toContain("page-column-wide");
  });

  it("supports a fill-height workspace without changing the default mode", async () => {
    const wrapper = mount(PageLayout, { props: { title: "Roles", fill: true } });
    expect(wrapper.classes()).toContain("page-layout-fill");
    await wrapper.setProps({ fill: false });
    expect(wrapper.classes()).not.toContain("page-layout-fill");
  });
});
