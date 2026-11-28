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
    expect(changed.min_confidence).toBeUndefined();
  });

  it("drops the minimum when the field is cleared, so each model keeps its own thresholds", async () => {
    const value = routerPolicyDefaults({ min_confidence: .8 });
    const wrapper = mount(RouterPolicyForm, { props: { modelValue: value, busy: false } });
    await wrapper.get('[data-test="router-confidence"]').setValue("");
    const changed = wrapper.emitted("update:modelValue")![0]![0] as typeof value;
    expect(changed.min_confidence).toBeUndefined();
  });

  it("rejects invalid confidence and deadlines", () => {
    expect(validateRouterPolicy(routerPolicyDefaults({ deadline_seconds: 31 }))).toContain("deadline");
    for (const min_confidence of [0, -1, 1.01, Number.NaN, Number.POSITIVE_INFINITY])
      expect(validateRouterPolicy(routerPolicyDefaults({ min_confidence }))).toContain("confidence");
    expect(validateRouterPolicy(routerPolicyDefaults())).toBe("");
  });

  it("edits the minimum confidence without changing deadlines", async () => {
    const wrapper = mount(RouterPolicyForm, { props: { modelValue: routerPolicyDefaults(), busy: false } });
    await wrapper.get('[data-test="router-confidence"]').setValue("0.8");
    expect(wrapper.emitted("update:modelValue")![0]![0]).toMatchObject({ min_confidence: .8, deadline_seconds: 10 });
  });

  it("disables changes while saving and says when the next model is asked", () => {
    const wrapper = mount(RouterPolicyForm, { props: { modelValue: routerPolicyDefaults(), busy: true } });
    expect(wrapper.get('[data-test="routing-deadline"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("The next one is asked when one fails");
  });
});
