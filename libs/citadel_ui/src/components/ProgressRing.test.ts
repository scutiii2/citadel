import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ProgressRing from "./ProgressRing.vue";

const arc = (percent: number, danger = false) => mount(ProgressRing, { props: { percent, danger } });

describe("ProgressRing", () => {
  it("fills the ring to the share, kept between nothing and full", () => {
    expect(arc(25).get(".arc").attributes("stroke-dasharray")).toBe("25 100");
    expect(arc(140).get(".arc").attributes("stroke-dasharray")).toBe("100 100");
    expect(arc(-3).find(".arc").exists()).toBe(false);
    expect(arc(0).find(".arc").exists()).toBe(false);
  });

  it("marks a ring in danger and stays out of the way of screen readers", () => {
    expect(arc(95, true).classes()).toContain("danger");
    expect(arc(10).classes()).not.toContain("danger");
    expect(arc(10).attributes("aria-hidden")).toBe("true");
  });
});
