import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { CapabilityInfo } from "../../api/CommandsClient";
import ToolScopePicker from "./ToolScopePicker.vue";

const cap = (name: string, tools: string[]): CapabilityInfo => ({ name, enabled: true, label: null, tools, resources: [] });
const CAPS = [cap("calc", ["tool_calc_add", "tool_calc_mul"]), cap("notes", ["tool_notes_list"]), cap("empty", [])];

function picker(modelValue: string) {
  return mount(ToolScopePicker, { props: { modelValue, capabilities: CAPS } });
}

describe("ToolScopePicker", () => {
  it("says every tool is sent while nothing limits the agent, and ticks nothing", () => {
    const wrapper = picker("");
    expect(wrapper.get("[data-test=tool-count]").text()).toContain("every tool (3)");
    expect(wrapper.get<HTMLInputElement>("[data-test=cap-calc]").element.checked).toBe(false);
    expect(wrapper.find("[data-test=cap-empty]").exists()).toBe(false);
  });

  it("counts the tools a list of globs lets through", () => {
    const wrapper = picker("tool_calc_*");
    expect(wrapper.get("[data-test=tool-count]").text()).toContain("2 tools sent");
    expect(wrapper.get<HTMLInputElement>("[data-test=cap-calc]").element.checked).toBe(true);
    expect(wrapper.get<HTMLInputElement>("[data-test=cap-notes]").element.checked).toBe(false);
  });

  it("starts an explicit list from the first tick and keeps hand-typed globs", async () => {
    const first = picker("");
    await first.get("[data-test=cap-notes]").setValue(true);
    expect(first.emitted("update:modelValue")![0]).toEqual(["tool_notes_list"]);

    const next = picker("tool_ticket_*, tool_notes_list");
    await next.get("[data-test=cap-calc]").setValue(true);
    expect(next.emitted("update:modelValue")![0]).toEqual(["tool_ticket_*, tool_notes_list, tool_calc_add, tool_calc_mul"]);
  });

  it("removes a capability's tools when it is unticked", async () => {
    const wrapper = picker("tool_calc_add, tool_calc_mul, tool_ticket_*");
    await wrapper.get("[data-test=cap-calc]").setValue(false);
    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["tool_ticket_*"]);
  });
});
