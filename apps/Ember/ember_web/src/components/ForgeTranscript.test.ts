import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { TranscriptItem } from "../utils/forgeTranscript";
import ForgeTranscript from "./ForgeTranscript.vue";

const items: TranscriptItem[] = [
  { key: "m1", kind: "user", seq: 1, text: "@claude fix it", time: "2026-10-18T10:00:00" },
  { key: "m2", kind: "tool", seq: 2, label: "claude", name: "Edit", summary: "app.py" },
  { key: "m3", kind: "permission", seq: 3, requestId: "r1", turnId: "t", label: "claude", tool: "Bash", summary: "npm test", status: "pending" },
  { key: "m4", kind: "worker", seq: 4, turnId: "t", label: "claude", provider: "claude", text: "Fixed **it**", streaming: false, partial: false, time: "2026-10-18T10:01:00", usage: { input_tokens: 3, output_tokens: 4 } },
  { key: "m5", kind: "system", seq: 5, text: "@codex is offline." },
];

describe("ForgeTranscript", () => {
  it("shows each kind of item", () => {
    const wrapper = mount(ForgeTranscript, { props: { items, running: false } });

    expect(wrapper.text()).toContain("@claude fix it");
    expect(wrapper.text()).toContain("Edit");
    expect(wrapper.text()).toContain("app.py");
    expect(wrapper.text()).toContain("@codex is offline.");
    expect(wrapper.get(".worker strong:not(.who)").text()).toBe("it");  // rendered as markdown
  });

  it("asks a pending permission with Allow and Deny", async () => {
    const wrapper = mount(ForgeTranscript, { props: { items, running: true } });

    expect(wrapper.text()).toContain("npm test");
    await wrapper.get("button.allow").trigger("click");
    await wrapper.get("button.deny").trigger("click");

    expect(wrapper.emitted("answer")).toEqual([["r1", true], ["r1", false]]);
  });

  it("shows a decided permission as text with an icon, without buttons", () => {
    const decided = items.map((item) => (item.kind === "permission" ? { ...item, status: "denied" as const } : item));
    const wrapper = mount(ForgeTranscript, { props: { items: decided, running: false } });

    expect(wrapper.find("button.allow").exists()).toBe(false);
    expect(wrapper.get(".permission").text()).toContain("Denied");
    expect(wrapper.find(".permission svg").exists()).toBe(true);
  });

  it("labels timed-out and allowed requests", () => {
    for (const [status, word] of [["allowed", "Allowed"], ["timed_out", "No answer"]] as const) {
      const changed = items.map((item) => (item.kind === "permission" ? { ...item, status } : item));
      expect(mount(ForgeTranscript, { props: { items: changed, running: false } }).get(".permission").text()).toContain(word);
    }
  });

  it("marks a streaming reply and a partial one", () => {
    const draft: TranscriptItem = { key: "d1", kind: "worker", seq: null, turnId: "t", label: "claude", provider: null, text: "Half", streaming: true, partial: false, time: null, usage: null };

    const streaming = mount(ForgeTranscript, { props: { items: [draft], running: true } });
    expect(streaming.get(".worker").text()).toContain("Writing");

    const partial = mount(ForgeTranscript, { props: { items: [{ ...draft, streaming: false, partial: true }], running: false } });
    expect(partial.get(".worker").text()).toContain("Partial answer");
  });

  it("says when nothing has been said", () => {
    expect(mount(ForgeTranscript, { props: { items: [], running: false } }).text()).toContain("Start with @");
  });
});
