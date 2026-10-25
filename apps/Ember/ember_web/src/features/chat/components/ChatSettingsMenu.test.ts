import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import ChatSettingsMenu from "./ChatSettingsMenu.vue";

const BASE = {
  caveman: false,
  independent: false,
  plan: true,
  planLean: true,
  askBeforeTools: false,
  forceToolApproval: false,
  chime: true,
  allowedCount: 0,
  enabledExtensions: [] as string[],
  attention: false,
  secondBrainAvailable: false,
  saveToSecondBrain: false,
  secondBrainPending: false,
};

let wrapper: ReturnType<typeof mount> | null = null;

function open(props: Partial<typeof BASE> = {}) {
  wrapper = mount(ChatSettingsMenu, {
    props: { ...BASE, ...props },
    attachTo: document.body,
    global: { stubs: { RouterLink: { props: ["to"], template: '<a :href="to"><slot /></a>' } } },
  });
  return wrapper;
}

afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

const gear = (w: ReturnType<typeof mount>) => w.get("button.gear");
const panel = (w: ReturnType<typeof mount>) => w.find(".panel");

describe("ChatSettingsMenu", () => {
  it("hides auto-save unless Obsidian is active", async () => {
    const w = open();
    await gear(w).trigger("click");
    expect(panel(w).text()).not.toContain("Save to second brain");
  });

  it("offers an off-by-default per-chat auto-save switch and emits changes", async () => {
    const w = open({ secondBrainAvailable: true });
    await gear(w).trigger("click");
    const label = w.findAll("label").find((l) => l.text().includes("Save to second brain"))!;
    expect((label.get("input").element as HTMLInputElement).checked).toBe(false);
    await label.get("input").setValue(true);
    expect(w.emitted("update:saveToSecondBrain")).toEqual([[true]]);
  });

  it("keeps the server-backed switch disabled while saving", async () => {
    const w = open({ secondBrainAvailable: true, secondBrainPending: true });
    await gear(w).trigger("click");
    const label = w.findAll("label").find((l) => l.text().includes("Save to second brain"))!;
    expect(label.get("input").attributes("disabled")).toBeDefined();
    expect(label.get("input").attributes("aria-busy")).toBe("true");
  });
  it("is closed on load, with only the gear showing", () => {
    const w = open();

    expect(panel(w).exists()).toBe(false);
    expect(gear(w).attributes("aria-expanded")).toBe("false");
  });

  it("says its switches apply instantly and stay on this device", async () => {
    const w = open();

    await gear(w).trigger("click");

    expect(panel(w).get(".note").text()).toBe("Applies instantly. Saved on this device.");
  });

  it("links to the full Settings page", async () => {
    const w = open();

    await gear(w).trigger("click");

    expect(panel(w).get("a.all-settings").attributes("href")).toBe("/settings");
  });

  it("opens and closes from the gear", async () => {
    const w = open();

    await gear(w).trigger("click");
    expect(panel(w).exists()).toBe(true);
    expect(gear(w).attributes("aria-expanded")).toBe("true");

    await gear(w).trigger("click");
    expect(panel(w).exists()).toBe(false);
  });

  it("closes on Escape and hands focus back to the gear", async () => {
    const w = open();
    await gear(w).trigger("click");

    await w.get(".panel").trigger("keydown", { key: "Escape" });
    await w.vm.$nextTick();

    expect(panel(w).exists()).toBe(false);
    expect(document.activeElement).toBe(gear(w).element);
  });

  it("closes on a click outside, but not on a click inside", async () => {
    const w = open();
    await gear(w).trigger("click");

    await w.get(".panel").trigger("click");
    expect(panel(w).exists()).toBe(true);

    document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await w.vm.$nextTick();
    expect(panel(w).exists()).toBe(false);
  });

  it("shows each setting and reports a change", async () => {
    const w = open();
    await gear(w).trigger("click");

    expect(w.findAll("label").map((l) => l.text())).toEqual([
      "Terse replies",
      "Independent prompts",
      "Task checklist",
      "Update only on change",
      "Chime when done",
    ]);
    const boxes = w.findAll("input[type=checkbox]");
    expect(boxes.map((b) => (b.element as HTMLInputElement).checked)).toEqual([false, false, true, true, true]);

    await boxes[0]!.setValue(true);
    await boxes[1]!.setValue(true);
    await boxes[2]!.setValue(false);
    await boxes[3]!.setValue(false);
    await boxes[4]!.setValue(false);

    expect(w.emitted("update:caveman")).toEqual([[true]]);
    expect(w.emitted("update:independent")).toEqual([[true]]);
    expect(w.emitted("update:plan")).toEqual([[false]]);
    expect(w.emitted("update:planLean")).toEqual([[false]]);
    expect(w.emitted("update:chime")).toEqual([[false]]);
  });

  it("puts each setting's token cost in its tooltip", async () => {
    const w = open();
    await gear(w).trigger("click");

    const titles = w.findAll("label").map((l) => l.attributes("title") ?? "");

    expect(titles).toHaveLength(5);
    for (const title of titles) expect(title).toMatch(/token/i);
    expect(titles[2]).toContain("200 input tokens");
  });

  it("hides 'Update only on change' while the task checklist is off", async () => {
    const w = open({ plan: false });
    await gear(w).trigger("click");

    expect(w.findAll("label").map((l) => l.text())).not.toContain("Update only on change");
  });

  it("no longer holds the tool approval switch: the picker next to it does", async () => {
    const w = open({ askBeforeTools: true });
    await gear(w).trigger("click");

    expect(w.findAll("label").map((l) => l.text())).not.toContain("Ask before tools");
  });

  it("hides the allowed-tools reset while an administrator forces approval", async () => {
    const w = open({ forceToolApproval: true, askBeforeTools: true, allowedCount: 2 });
    await gear(w).trigger("click");

    expect(w.find("button.allowed").exists()).toBe(false);
  });

  it("offers to reset allowed tools only while asking and some are allowed", async () => {
    const w = open({ askBeforeTools: true, allowedCount: 2 });
    await gear(w).trigger("click");

    const reset = w.get("button.allowed");
    expect(reset.text()).toBe("2 tools allowed - reset");
    await reset.trigger("click");
    expect(w.emitted("clear-allowed")).toHaveLength(1);
  });

  it("names the enabled extensions and links to the page", async () => {
    const w = open({ enabledExtensions: ["pdf", "fs"] });
    await gear(w).trigger("click");

    const link = w.get("a.extensions");
    expect(link.text()).toBe("Extensions: pdf, fs");
    expect(link.attributes("href")).toBe("/capabilities?tab=extensions");
  });

  it("says extensions are off when none are enabled", async () => {
    const w = open();
    await gear(w).trigger("click");

    expect(w.get("a.extensions").text()).toBe("Extensions: off");
  });

  it("marks the gear only when something needs attention", () => {
    expect(open({ attention: true }).find(".dot").exists()).toBe(true);
    wrapper?.unmount();
    expect(open().find(".dot").exists()).toBe(false);
  });
});
