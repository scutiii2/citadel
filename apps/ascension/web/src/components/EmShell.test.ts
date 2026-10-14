import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmShell from "./EmShell.vue";

describe("EmShell", () => {
  it("shows one header with the logo, wallet and content", () => {
    const wrapper = mount(EmShell, { props: { insignia: 240 }, slots: { default: "<p class='body'>Hello</p>" } });

    expect(wrapper.find("h1").attributes("aria-label")).toBe("ASCENSION");
    expect(wrapper.find('.destination').exists()).toBe(false);
    expect(wrapper.find('.navigation').text()).toBe('');
    expect(wrapper.find('.screen-heading').exists()).toBe(false);
    expect(wrapper.find(".wallet").text()).toBe("");
    expect(wrapper.find(".wallet").attributes("data-label")).toBe("240 Insignia");
    expect(wrapper.find(".body").text()).toBe("Hello");
  });

  it("has no wallet before there is a profile", () => {
    const wrapper = mount(EmShell, { props: { insignia: null } });

    expect(wrapper.find(".wallet").exists()).toBe(false);
  });
});
