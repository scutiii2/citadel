import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appConfigClient, type AppConfig } from "../api/AppConfigClient";
import AppConfigCard from "./AppConfigCard.vue";

const VIEW: AppConfig = {
  session_hours: 12, default_role: "Member",
  rate_limit: { enabled: true, scope: "both", max_attempts: 5, window_seconds: 900, lockout_seconds: 900 },
  ip_filter: { allow_list: [], deny_list: ["10.0.0.0/8"] },
  headers: { enabled: true, hsts_max_age: 0 },
  fingerprint: { enabled: true, signals: ["user_agent", "accept_language", "ip_subnet"] },
  backup: { enabled: true, keep: 14, every_hours: 24 },
  stored: ["backup"],
};

beforeEach(() => {
  vi.spyOn(appConfigClient, "get").mockResolvedValue(VIEW);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(AppConfigCard, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const field = (wrapper: Awaited<ReturnType<typeof mounted>>, name: string) => wrapper.get(`[data-test="${name}"]`);

describe("AppConfigCard", () => {
  it("shows the values and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((field(wrapper, "session_hours").element as HTMLInputElement).value).toBe("12");
    expect((field(wrapper, "deny").element as HTMLTextAreaElement).value).toBe("10.0.0.0/8");
    expect(field(wrapper, "save").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).not.toContain("Accounts must verify their email");
    wrapper.unmount();
  });

  it("sends only what changed, a group with only its changed fields", async () => {
    const save = vi.spyOn(appConfigClient, "save").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await field(wrapper, "session_hours").setValue("4");
    await field(wrapper, "rl_max").setValue("3");
    await field(wrapper, "deny").setValue("10.0.0.0/8\n192.168.0.0/16");
    await field(wrapper, "signal-ip_subnet").setValue(false);
    await field(wrapper, "form").trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({
      session_hours: 4, rate_limit: { max_attempts: 3 }, ip_filter: { deny_list: ["10.0.0.0/8", "192.168.0.0/16"] },
      fingerprint: { signals: ["user_agent", "accept_language"] },
    });
    expect(field(wrapper, "notice").text()).toContain("next start");
    wrapper.unmount();
  });

  it("puts every saved setting back to the default with null", async () => {
    const save = vi.spyOn(appConfigClient, "save").mockResolvedValue({ ...VIEW, stored: [] });
    const wrapper = await mounted();
    await field(wrapper, "defaults").trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ backup: null });
    expect(wrapper.find('[data-test="defaults"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows the refusal and keeps what was typed", async () => {
    vi.spyOn(appConfigClient, "save").mockRejectedValue(new Error("Session length must be a whole number, 1 or more."));
    const wrapper = await mounted();
    await field(wrapper, "session_hours").setValue("0");
    await field(wrapper, "form").trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Session length");
    expect((field(wrapper, "session_hours").element as HTMLInputElement).value).toBe("0");
    wrapper.unmount();
  });
});
