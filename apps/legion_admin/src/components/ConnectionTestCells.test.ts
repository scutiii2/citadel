import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import ConnectionTestCells from "./ConnectionTestCells.vue";

const mountRow = (run: () => Promise<unknown>) => mount({
  components: { ConnectionTestCells },
  setup: () => ({ run }),
  template: '<table><tbody><tr><ConnectionTestCells label="Bard" :run="run" /></tr></tbody></table>',
});

describe("ConnectionTestCells", () => {
  it("shows a check for a connection that answers, and no words", async () => {
    let finish: (value: unknown) => void = () => {};
    const run = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    const wrapper = mountRow(run);
    expect(wrapper.get(".idle").attributes("aria-label")).toBe("Not tested");
    await wrapper.get('[aria-label="Test Bard"]').trigger("click");
    expect(wrapper.find('[data-test="testing"]').exists()).toBe(true);
    expect(wrapper.get('[aria-label="Test Bard"]').classes()).toContain("running");
    finish({ ok: true, message: "The provider accepted the credentials." });
    await flushPromises();
    const result = wrapper.get('[data-test="test-result"]');
    expect(result.classes()).toContain("ok");
    expect(result.attributes("aria-label")).toBe("Connected");
    expect(result.text()).toBe("");
    expect(wrapper.get('[data-test="test-popover"]').text()).toContain("accepted the credentials");
  });

  it("shows a cross and the error code, with what it means in the popover", async () => {
    const run = vi.fn().mockResolvedValue({ ok: false, code: "401", message: "The key was refused." });
    const wrapper = mountRow(run);
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-test="test-code"]').text()).toBe("401");
    expect(wrapper.get('[data-test="test-result"]').attributes("aria-label")).toBe("Failed, code 401");
    expect(wrapper.get('[data-test="test-popover"]').text()).toContain("The key was refused.");
  });

  it("lists each address when a server has several, and falls back to ERR when the test itself fails", async () => {
    const run = vi.fn().mockResolvedValueOnce({ ok: false, code: "503", message: "Some addresses do not answer.",
      origins: [{ ok: true, message: "The server answers." }, { ok: false, code: "503", message: "The server answered 503." }] })
      .mockRejectedValueOnce(new Error("Legion is unreachable"));
    const wrapper = mountRow(run);
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-test="test-popover"]').text()).toContain("Address 2: The server answered 503.");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-test="test-code"]').text()).toBe("ERR");
    expect(wrapper.get('[data-test="test-popover"]').text()).toContain("Legion is unreachable");
  });
});
