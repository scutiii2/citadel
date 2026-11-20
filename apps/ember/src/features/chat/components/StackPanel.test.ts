import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StackPanel from "./StackPanel.vue";
import type { StackItem, StackView } from "../api/StackClient";

const item = (id: number, text: string, pinned = false, source = "agent"): StackItem => ({ id, text, pinned, source, at: "2026-01-01T00:00:00Z" });
const view = (items: StackItem[], extra: Partial<StackView> = {}): StackView => ({ items, used: items.length, limit: 40, warn: false, full: false, ...extra });

function mountPanel(props: Partial<InstanceType<typeof StackPanel>["$props"]> = {}) {
  return mount(StackPanel, {
    props: {
      status: "ready", view: view([item(1, "I live in Paris", false, "user"), item(2, "Never email Bo", true), item(3, "Older facts, summed up", false, "compaction")]),
      error: "", addError: "", pending: false, compacting: false, notice: "", locked: false, ...props,
    },
  });
}

describe("StackPanel", () => {
  it("lists the items with their source, and marks a pinned one with text as well as an icon", () => {
    const w = mountPanel();
    const rows = w.findAll("[data-test=stack-item]");
    expect(rows).toHaveLength(3);
    expect(rows[0]!.text()).toContain("I live in Paris");
    expect(rows[0]!.text()).toContain("You");
    expect(rows[1]!.text()).toContain("Pinned");
    expect(rows[1]!.get("[data-test=pin]").attributes("aria-pressed")).toBe("true");
    expect(rows[1]!.get("[data-test=pin]").attributes("aria-label")).toBe("Unpin item");
    expect(rows[2]!.text()).toContain("Summary");
    expect(w.get(".summary").text()).toContain("3 of 40 items");
  });

  it("renders item text as text, never as HTML", () => {
    const w = mountPanel({ view: view([item(1, "<img src=x onerror=alert(1)>")]) });
    expect(w.find("img").exists()).toBe(false);
    expect(w.get("[data-test=stack-item]").text()).toContain("<img");
  });

  it("warns when nearly full and when full, with an icon and text", () => {
    const warn = mountPanel({ view: view([item(1, "a")], { warn: true }) });
    expect(warn.get("[data-test=stack-warn]").text()).toContain("compact it now");
    expect(warn.get("[data-test=stack-warn]").find("svg").exists()).toBe(true);
    expect(warn.find("[data-test=stack-full]").exists()).toBe(false);
    const full = mountPanel({ view: view([item(1, "a")], { warn: true, full: true }) });
    expect(full.get("[data-test=stack-full]").text()).toContain("drops the oldest unpinned");
    expect(full.find("[data-test=stack-warn]").exists()).toBe(false);
    expect(mountPanel().find("[data-test=stack-warn]").exists()).toBe(false);
  });

  it("emits what the user does", async () => {
    const w = mountPanel();
    await w.findAll("[data-test=pin]")[0]!.trigger("click");
    await w.findAll("[data-test=pin]")[1]!.trigger("click");
    await w.findAll("[data-test=remove]")[2]!.trigger("click");
    await w.get("[data-test=compact]").trigger("click");
    expect(w.emitted("pin")).toEqual([[1, true], [2, false]]);
    expect(w.emitted("remove")).toEqual([[3]]);
    expect(w.emitted("compact")).toHaveLength(1);
  });

  it("compacting is off while busy, locked, or when only pinned items remain", () => {
    expect(mountPanel({ compacting: true }).get("[data-test=compact]").attributes("disabled")).toBeDefined();
    expect(mountPanel({ compacting: true }).get("[data-test=compact]").attributes("aria-busy")).toBe("true");
    expect(mountPanel({ pending: true }).get("[data-test=compact]").attributes("disabled")).toBeDefined();
    const locked = mountPanel({ locked: true });
    expect(locked.get("[data-test=compact]").attributes("disabled")).toBeDefined();
    expect(locked.text()).toContain("Available when the answer is done");
    const pinnedOnly = mountPanel({ view: view([item(1, "a", true)]) });
    expect(pinnedOnly.get("[data-test=compact]").attributes("disabled")).toBeDefined();
    expect(pinnedOnly.get("[data-test=compact]").attributes("title")).toBe("Nothing to compact");
    expect(mountPanel().get("[data-test=compact]").attributes("disabled")).toBeUndefined();
  });

  it("shows the compaction result and a failure", () => {
    expect(mountPanel({ notice: "Replaced 8 items with a summary." }).text()).toContain("Replaced 8 items with a summary.");
    const failed = mountPanel({ error: "The context summarizer did not answer." });
    expect(failed.get("[data-test=stack-error]").text()).toContain("did not answer");
    expect(failed.get("[data-test=stack-error]").attributes("role")).toBe("alert");
  });

  it("add: Enter submits the trimmed text, Shift+Enter does not, and the text stays until cleared", async () => {
    const w = mountPanel();
    const field = w.get("[data-test=add-text]");
    await field.setValue("  Prefers metric  ");
    await field.trigger("keydown", { key: "Enter", shiftKey: true });
    expect(w.emitted("add")).toBeUndefined();
    await field.trigger("keydown", { key: "Enter" });
    expect(w.emitted("add")).toEqual([["Prefers metric"]]);
    expect((field.element as HTMLTextAreaElement).value).toBe("  Prefers metric  ");
    (w.vm as unknown as { clearDraft: () => void }).clearDraft();
    await w.vm.$nextTick();
    expect((field.element as HTMLTextAreaElement).value).toBe("");
  });

  it("add is off for empty text and while busy; a refusal sits beside the field", async () => {
    const w = mountPanel();
    expect(w.get("button[type=submit]").attributes("disabled")).toBeDefined();
    await w.get("[data-test=add-text]").setValue("x");
    expect(w.get("button[type=submit]").attributes("disabled")).toBeUndefined();
    await w.setProps({ pending: true });
    expect(w.get("button[type=submit]").attributes("disabled")).toBeDefined();
    await w.setProps({ pending: false, addError: "An item holds at most 500 characters." });
    const field = w.get("[data-test=add-text]");
    expect(field.attributes("aria-invalid")).toBe("true");
    expect(w.get("[data-test=add-error]").text()).toContain("at most 500");
    expect(field.attributes("aria-describedby")).toBe(w.get("[data-test=add-error]").attributes("id"));
  });

  it("shows loading, a retryable load error, an unsaved chat and an empty list", async () => {
    expect(mountPanel({ status: "loading", view: null }).text()).toContain("Loading memory");
    const failed = mountPanel({ status: "error", view: null, error: "Storage is unavailable" });
    expect(failed.text()).toContain("Storage is unavailable");
    await failed.get("button.chip").trigger("click");
    expect(failed.emitted("retry")).toHaveLength(1);
    expect(mountPanel({ status: "missing", view: null }).text()).toContain("Send a message first");
    expect(mountPanel({ view: view([]) }).text()).toContain("Nothing is remembered in this chat yet");
  });
});
