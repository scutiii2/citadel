import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ForgeComposer from "./ForgeComposer.vue";

function setup(props: Partial<InstanceType<typeof ForgeComposer>["$props"]> = {}, text = "") {
  return mount(ForgeComposer, {
    props: {
      labels: ["claude", "codex"], running: false, busy: false, disabledReason: "", error: "",
      modelValue: text, "onUpdate:modelValue": (value: string) => wrapper.setProps({ modelValue: value }),
      ...props,
    },
    attachTo: document.body,
  });
}
let wrapper: ReturnType<typeof setup>;

async function type(text: string) {
  const field = wrapper.get("textarea");
  const element = field.element as HTMLTextAreaElement;
  element.value = text;
  element.setSelectionRange(text.length, text.length);
  await field.trigger("input");
}

describe("ForgeComposer", () => {
  it("sends on Enter and keeps Shift+Enter for a new line", async () => {
    wrapper = setup({}, "hello");

    await wrapper.get("textarea").trigger("keydown", { key: "Enter", shiftKey: true });
    expect(wrapper.emitted("send")).toBeUndefined();

    await wrapper.get("textarea").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("send")).toHaveLength(1);
  });

  it("does not send a blank message, while busy, while a turn runs, or when disabled", async () => {
    const cases = [
      { props: {}, text: "   " },
      { props: { busy: true }, text: "hello" },
      { props: { running: true }, text: "hello" },
      { props: { disabledReason: "Invite a worker first." }, text: "hello" },
    ];
    for (const { props, text } of cases) {
      wrapper = setup(props, text);
      await wrapper.get("textarea").trigger("keydown", { key: "Enter" });
      expect(wrapper.emitted("send")).toBeUndefined();
    }
  });

  it("offers workers when @ is typed and completes with Enter", async () => {
    wrapper = setup();
    await type("@c");

    const options = wrapper.findAll("[role=option]");
    expect(options.map((o) => o.text())).toEqual(["@claude", "@codex"]);

    await wrapper.get("textarea").trigger("keydown", { key: "ArrowDown" });
    await wrapper.get("textarea").trigger("keydown", { key: "Enter" });

    expect(wrapper.props("modelValue")).toBe("@codex ");
    expect(wrapper.emitted("send")).toBeUndefined();  // Enter picked, it did not send
  });

  it("narrows the menu as the handle is typed, and Escape closes it", async () => {
    wrapper = setup();
    await type("@cod");
    expect(wrapper.findAll("[role=option]").map((o) => o.text())).toEqual(["@codex"]);

    await wrapper.get("textarea").trigger("keydown", { key: "Escape" });
    expect(wrapper.find("[role=listbox]").exists()).toBe(false);
  });

  it("clicking a suggestion completes it", async () => {
    wrapper = setup();
    await type("hi @cl");

    await wrapper.findAll("[role=option]")[0]!.trigger("mousedown");

    expect(wrapper.props("modelValue")).toBe("hi @claude ");
  });

  it("swaps Send for Stop while a turn runs", async () => {
    wrapper = setup({ running: true }, "x");

    expect(wrapper.find("button.send").exists()).toBe(false);
    await wrapper.get("button.stop").trigger("click");

    expect(wrapper.emitted("stop")).toHaveLength(1);
  });

  it("shows the reason it is disabled, and an error", () => {
    wrapper = setup({ disabledReason: "Invite a worker first.", error: "A worker is still answering." });

    expect(wrapper.text()).toContain("Invite a worker first.");
    expect(wrapper.get("[role=alert]").text()).toContain("A worker is still answering.");
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).disabled).toBe(true);
  });
});
