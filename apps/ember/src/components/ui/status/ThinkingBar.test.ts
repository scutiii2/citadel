import { mount } from "@vue/test-utils";
import { expect, it } from "vitest";
import ThinkingBar from "./ThinkingBar.vue";

it("is decorative: hidden from assistive technology", () => {
  expect(mount(ThinkingBar).attributes("aria-hidden")).toBe("true");
});
