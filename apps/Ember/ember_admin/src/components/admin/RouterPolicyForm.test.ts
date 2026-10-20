import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RouterPolicyForm from "./RouterPolicyForm.vue";
import { routerPolicyDefaults, validateRouterPolicy } from "../../utils/routerPolicy";

describe("Router policy", () => {
  it("edits the deadline and keeps independent settings", async () => {
    const value = routerPolicyDefaults();
    const wrapper = mount(RouterPolicyForm, { props: { modelValue: value, busy: false } });
    await wrapper.get('[data-test="routing-deadline"]').setValue("8");
    const changed = wrapper.emitted("update:modelValue")![0]![0] as typeof value;
    expect(changed.deadline_seconds).toBe(8);
    expect(changed.choose_agent).toBe(true);
    expect(changed.thresholds["2"].jev).toBe(.9);
  });

  it("rejects invalid thresholds, deadlines and an empty voting policy", () => {
    expect(validateRouterPolicy(routerPolicyDefaults({ deadline_seconds: 31 }))).toContain("deadline");
    expect(validateRouterPolicy(routerPolicyDefaults({ english: false, typed: false, fallback: false }))).toContain("voter");
    const policy = routerPolicyDefaults();
    policy.thresholds["2"].jev = Number.NaN;
    expect(validateRouterPolicy(policy)).toContain("threshold");
  });

  it("disables changes while saving and displays local versus fallback models", () => {
    const wrapper = mount(RouterPolicyForm, { props: { modelValue: routerPolicyDefaults(), busy: true } });
    expect(wrapper.get('[data-test="routing-deadline"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Laya English");
    expect(wrapper.text()).toContain("Jev");
  });
});
