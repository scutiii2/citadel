import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import WavyProgress from "./WavyProgress.vue";

describe("WavyProgress", () => {
  it("is one named progress bar whose value, width and semantics agree", () => {
    const wrapper = mount(WavyProgress, { props: { label: "Download progress", value: 40 } });
    const bar = wrapper.get("[role=progressbar]");
    expect(bar.attributes("aria-label")).toBe("Download progress");
    expect(bar.attributes("aria-valuenow")).toBe("40");
    expect(bar.attributes("style")).toContain("--p: 0.4");
    expect(wrapper.findAll("[aria-hidden=true]").length).toBe(2);
  });

  it("collapses the gap at 0 and 100 percent and clamps strays", () => {
    expect(mount(WavyProgress, { props: { label: "x", value: 0 } }).classes()).toContain("empty");
    expect(mount(WavyProgress, { props: { label: "x", value: 100 } }).classes()).toContain("full");
    expect(mount(WavyProgress, { props: { label: "x", value: 250 } }).attributes("aria-valuenow")).toBe("100");
  });

  it("reports no value while progress is unknown", () => {
    const wrapper = mount(WavyProgress, { props: { label: "x", value: null } });
    expect(wrapper.attributes("aria-valuenow")).toBeUndefined();
  });
});
