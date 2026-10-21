import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import PasswordInput from "./PasswordInput.vue";

it("reveals and hides the same password, preserving native form attributes and edits", async () => {
  const wrapper = mount(PasswordInput, {
    props: { label: "New password", modelValue: "initial-password" },
    attrs: { autocomplete: "new-password", minlength: "8", required: true, name: "password" },
  });
  const input = wrapper.get("input");
  expect(input.attributes()).toMatchObject({ type: "password", autocomplete: "new-password", minlength: "8", required: "", name: "password" });
  expect(wrapper.get("label").attributes("for")).toBe(input.attributes("id"));
  expect(wrapper.get("button").attributes("type")).toBe("button");
  await wrapper.get("button").trigger("click");
  expect(input.attributes("type")).toBe("text");
  expect(input.element.value).toBe("initial-password");
  expect(wrapper.get("button").attributes("aria-label")).toBe("Hide password");
  expect(wrapper.get("button").attributes("aria-pressed")).toBe("true");
  await input.setValue("edited-password");
  expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["edited-password"]);
  await wrapper.setProps({ modelValue: "edited-password" });
  await wrapper.get("button").trigger("click");
  expect(input.attributes("type")).toBe("password");
  expect(input.element.value).toBe("edited-password");
  expect(wrapper.get("button").attributes("aria-pressed")).toBe("false");
});

it("keeps each field's visibility and label association independent", async () => {
  const wrapper = mount({ components: { PasswordInput }, template: '<PasswordInput label="New password" /><PasswordInput label="Repeat password" />' });
  const inputs = wrapper.findAll("input");
  expect(inputs[0]!.attributes("id")).not.toBe(inputs[1]!.attributes("id"));
  await wrapper.findAll("button")[0]!.trigger("click");
  expect(inputs.map(input => input.attributes("type"))).toEqual(["text", "password"]);
});

it("disables both input and visibility button when disabled", () => {
  const wrapper = mount(PasswordInput, { props: { label: "Password", disabled: true } });
  expect(wrapper.get("input").element.disabled).toBe(true);
  expect(wrapper.get("button").element.disabled).toBe(true);
});
