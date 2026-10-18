import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { ForgeGroup } from "../api/ForgeClient";
import ForgeGroupList from "./ForgeGroupList.vue";

const group = (id: number, extra: Partial<ForgeGroup> = {}): ForgeGroup => ({
  id, title: `Group ${id}`, mode: "ask", relay: false, running: false, created_at: "2026-10-18T10:00:00", members: [], ...extra,
});

describe("ForgeGroupList", () => {
  it("lists groups with their worker counts and marks the open one", () => {
    const wrapper = mount(ForgeGroupList, {
      props: { groups: [group(1, { members: [{ worker_id: 1, label: "claude", provider: "claude", folder: "C:/x", online: true }] }), group(2)], selectedId: 2 },
    });

    expect(wrapper.text()).toContain("Group 1");
    expect(wrapper.text()).toContain("1 worker");
    expect(wrapper.text()).toContain("0 workers");
    const current = wrapper.findAll("button.group").filter((b) => b.attributes("aria-current") === "true");
    expect(current).toHaveLength(1);
    expect(current[0]!.text()).toContain("Group 2");
  });

  it("says a group is working, with text and not colour alone", () => {
    const wrapper = mount(ForgeGroupList, { props: { groups: [group(1, { running: true })], selectedId: null } });

    expect(wrapper.get("button.group").text()).toContain("Working");
  });

  it("emits select and create", async () => {
    const wrapper = mount(ForgeGroupList, { props: { groups: [group(5)], selectedId: null } });

    await wrapper.get("button.group").trigger("click");
    await wrapper.get("button.new").trigger("click");

    expect(wrapper.emitted("select")).toEqual([[5]]);
    expect(wrapper.emitted("create")).toHaveLength(1);
  });

  it("invites the user to make a first group", () => {
    const wrapper = mount(ForgeGroupList, { props: { groups: [], selectedId: null } });

    expect(wrapper.text()).toContain("No groups yet");
  });
});
