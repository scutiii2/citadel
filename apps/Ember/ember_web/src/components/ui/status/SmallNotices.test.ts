import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import CharacterCount from "./CharacterCount.vue";
import DangerZone from "./DangerZone.vue";
import RetentionNote from "./RetentionNote.vue";

describe("CharacterCount", () => {
  it("shows length over max with an optional unit and keeps the id", () => {
    const w = mount(CharacterCount, { props: { length: 3, max: 120 }, attrs: { id: "count" } });
    expect(w.text()).toBe("3/120");
    expect(w.attributes("id")).toBe("count");
    expect(mount(CharacterCount, { props: { length: 1, max: 9, suffix: " characters" } }).text()).toBe("1/9 characters");
  });
});

describe("DangerZone", () => {
  it("shows the label text and the button", () => {
    const w = mount(DangerZone, { props: { label: "Remove this file" }, slots: { default: "<button>Delete</button>" } });
    expect(w.text()).toContain("Remove this file");
    expect(w.get("button").text()).toBe("Delete");
  });

  it("lets the label slot replace the text", () => {
    const w = mount(DangerZone, { slots: { label: "<b>Danger zone</b>", default: "<button>Go</button>" } });
    expect(w.get("b").text()).toBe("Danger zone");
  });
});

describe("RetentionNote", () => {
  it("shows the slot text next to a hidden icon", () => {
    const w = mount(RetentionNote, { slots: { default: "Kept for 6 hours." } });
    expect(w.text()).toBe("Kept for 6 hours.");
    expect(w.get("svg").attributes("aria-hidden")).toBe("true");
  });
});
