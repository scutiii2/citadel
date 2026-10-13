import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmShell from "./EmShell.vue";

describe("EmShell", () => {
  it("shows one header with the logo, destination, wallet and content", () => {
    const wrapper = mount(EmShell, { props: { insignia: 240 }, slots: { default: "<p class='body'>Hello</p>" } });

    expect(wrapper.find("h1").text()).toBe("ASCENSION");
    expect(wrapper.find('.destination').text()).toBe('Main menu');
    expect(wrapper.find('.screen-heading').exists()).toBe(false);
    expect(wrapper.find(".wallet").text()).toBe("240 Insignia");
    expect(wrapper.find(".body").text()).toBe("Hello");
  });

  it("has no wallet before there is a profile", () => {
    const wrapper = mount(EmShell, { props: { insignia: null } });

    expect(wrapper.find(".wallet").exists()).toBe(false);
  });
});
