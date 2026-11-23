import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import ConnectionTest from "./ConnectionTest.vue";

describe("ConnectionTest", () => {
  it("shows the answer of a passing test, and each address when there are several", async () => {
    const run = vi.fn().mockResolvedValue({ ok: false, message: "Some addresses do not answer.", origins: [{ ok: true, message: "The server answers." }, { ok: false, message: "The token was refused." }] });
    const wrapper = mount(ConnectionTest, { props: { label: "Bard", run } });
    await wrapper.get('[aria-label="Test Bard"]').trigger("click");
    await flushPromises();
    expect(run).toHaveBeenCalledOnce();
    expect(wrapper.get('[data-test="test-result"]').text()).toContain("Some addresses do not answer.");
    expect(wrapper.text()).toContain("Address 2: The token was refused.");
  });

  it("shows why the test itself failed and allows another try", async () => {
    const run = vi.fn().mockRejectedValueOnce(new Error("Legion is down")).mockResolvedValue({ ok: true, message: "The gateway answers and is ready." });
    const wrapper = mount(ConnectionTest, { props: { label: "ConversationGateway", run } });
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-test="test-failure"]').text()).toContain("Legion is down");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-test="test-result"]').text()).toContain("ready");
  });
});
