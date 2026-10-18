import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { ForgeGroup } from "../api/ForgeClient";
import ForgeMembersPanel from "./ForgeMembersPanel.vue";

const group = (extra: Partial<ForgeGroup> = {}): ForgeGroup => ({
  id: 1, title: "Build", mode: "ask", relay: false, running: false, created_at: "2026-10-18T10:00:00",
  members: [
    { worker_id: 1, label: "claude", provider: "claude", folder: "C:/site", online: true },
    { worker_id: 2, label: "codex", provider: "codex", folder: "D:/site", online: false },
  ],
  ...extra,
});

const setup = (extra: Partial<ForgeGroup> = {}) => mount(ForgeMembersPanel, { props: { group: group(extra), busy: false }, attachTo: document.body });
const modeButton = (wrapper: ReturnType<typeof setup>, label: string) => wrapper.findAll("button").find((b) => b.text() === label)!;

describe("ForgeMembersPanel", () => {
  it("lists members with their folder and whether they are online, in text", () => {
    const wrapper = setup();

    expect(wrapper.text()).toContain("@claude");
    expect(wrapper.text()).toContain("C:/site");
    expect(wrapper.text()).toContain("Online");
    expect(wrapper.text()).toContain("Offline");
  });

  it("changes between ordinary modes at once", async () => {
    const wrapper = setup();

    await modeButton(wrapper, "Plan").trigger("click");

    expect(wrapper.emitted("mode")).toEqual([["plan"]]);
  });

  it("asks the parent to confirm full auto instead of applying it", async () => {
    const wrapper = setup();

    await modeButton(wrapper, "Full auto").trigger("click");

    expect(wrapper.emitted("full-auto")).toHaveLength(1);
    expect(wrapper.emitted("mode")).toBeUndefined();
  });

  it("explains the current mode", () => {
    expect(setup({ mode: "plan" }).text()).toContain("read and plan");
  });

  it("toggles relay", async () => {
    const wrapper = setup();

    await wrapper.get("input[role=switch]").setValue(true);

    expect(wrapper.emitted("relay")).toEqual([[true]]);
  });

  it("emits invite, remove and delete", async () => {
    const wrapper = setup();

    await modeButton(wrapper, "Invite a worker").trigger("click");
    await wrapper.get("button.remove").trigger("click");
    await modeButton(wrapper, "Delete group").trigger("click");

    expect(wrapper.emitted("invite")).toHaveLength(1);
    expect(wrapper.emitted("remove")).toEqual([[1]]);
    expect(wrapper.emitted("delete")).toHaveLength(1);
  });

  it("says when nobody has been invited", () => {
    expect(setup({ members: [] }).text()).toContain("No workers yet");
  });
});


describe("ForgeMembersPanel folders", () => {
  it("changes a member's folder", async () => {
    const wrapper = setup();

    await wrapper.get("button.change").trigger("click");
    await wrapper.get("input[type=text]").setValue("  D:/other  ");
    await wrapper.get("button.save").trigger("click");

    expect(wrapper.emitted("folder")).toEqual([[1, "D:/other"]]);
    expect(wrapper.find("input[type=text]").exists()).toBe(false);
  });

  it("can be cancelled without changing anything", async () => {
    const wrapper = setup();

    await wrapper.get("button.change").trigger("click");
    await wrapper.get(".edit-actions .cancel").trigger("click");

    expect(wrapper.emitted("folder")).toBeUndefined();
    expect(wrapper.find("code.folder").exists()).toBe(true);
  });

  it("will not change the folder while a worker is answering", () => {
    const wrapper = setup({ running: true });

    expect(wrapper.get("button.change").attributes("disabled")).toBeDefined();
  });
});
