import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmShell from "./EmShell.vue";

describe("EmShell", () => {
  it("shows one header with the logo, wallet and content", () => {
    const wrapper = mount(EmShell, { props: { insignia: 240 }, slots: { default: "<p class='body'>Hello</p>" } });

    expect(wrapper.find("h1").attributes("aria-label")).toBe("ASCENSION");
    expect(wrapper.find('.destination').exists()).toBe(false);
    expect(wrapper.find('.navigation').text()).toBe('ASCENSION');
    expect(wrapper.find('.screen-heading').exists()).toBe(false);
    expect(wrapper.find(".wallet").text()).toBe("240");
    expect(wrapper.find(".wallet").attributes("aria-label")).toBe("240 Insignia");
    expect(wrapper.find(".body").text()).toBe("Hello");
  });

  it("places the numeric balance immediately before a separate shop action", async () => {
    const wrapper = mount(EmShell, { props: { insignia: 2546, shopEnabled: true, shopOpen: true } });
    expect(wrapper.get('.wallet').text()).toBe('2,546');
    expect(wrapper.get('.wallet').element.nextElementSibling).toBe(wrapper.get('button.shop-action').element);
    expect(wrapper.get('button.shop-action').attributes('aria-pressed')).toBe('true');
    await wrapper.get('button.shop-action').trigger('click');
    expect(wrapper.emitted('shop')).toHaveLength(1);
  });

  it("has no wallet before there is a profile", () => {
    const wrapper = mount(EmShell, { props: { insignia: null } });

    expect(wrapper.find(".wallet").exists()).toBe(false);
  });
});
