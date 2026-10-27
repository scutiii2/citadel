import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StateMessage from "./StateMessage.vue";

describe("StateMessage", () => {
  it("shows loading as a status line", () => {
    const w = mount(StateMessage, { props: { kind: "loading" }, slots: { default: "Loading…" } });
    expect(w.get("[role=status]").text()).toBe("Loading…");
  });

  it("shows an error alert whose button asks to retry", async () => {
    const w = mount(StateMessage, { props: { kind: "error" }, slots: { default: "Offline" } });
    expect(w.get("[role=alert]").text()).toContain("Offline");
    await w.get("button").trigger("click");
    expect(w.emitted("retry")).toHaveLength(1);
  });

  it("shows an empty state with title and action", () => {
    const w = mount(StateMessage, { props: { kind: "empty", title: "Nothing" }, slots: { default: "Add one.", action: "<button>Add</button>" } });
    expect(w.get("h3").text()).toBe("Nothing");
    expect(w.text()).toContain("Add one.");
    expect(w.get("button").text()).toBe("Add");
  });
});
