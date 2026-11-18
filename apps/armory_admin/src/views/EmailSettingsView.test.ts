import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emailSettingsClient, type EmailSettings } from "../api/EmailSettingsClient";
import EmailSettingsView from "./EmailSettingsView.vue";

const SAVED: EmailSettings = {
  configured: true, smtp_server: "smtp.example.com", smtp_port: 587, security: "", from: "a@example.com",
  to: ["team@example.com"], allowed_recipient_domains: [], has_password: true,
};

afterEach(() => vi.restoreAllMocks());

async function mounted(view: EmailSettings = SAVED) {
  vi.spyOn(emailSettingsClient, "get").mockResolvedValue(view);
  const wrapper = mount(EmailSettingsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const field = (wrapper: Awaited<ReturnType<typeof mounted>>, name: string) => wrapper.get(`[data-test="${name}"]`);

describe("EmailSettingsView", () => {
  it("shows the saved values, keeps the password out and Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((field(wrapper, "server").element as HTMLInputElement).value).toBe("smtp.example.com");
    expect((field(wrapper, "to").element as HTMLTextAreaElement).value).toBe("team@example.com");
    expect(field(wrapper, "password-state").text()).toContain("A password is saved");
    expect(field(wrapper, "save").attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("says when email is not set up", async () => {
    const wrapper = await mounted({ configured: false });
    expect(field(wrapper, "empty").text()).toContain("not set up");
    wrapper.unmount();
  });

  it("sends only what changed, with the port as a number and lists split by line", async () => {
    const save = vi.spyOn(emailSettingsClient, "save").mockResolvedValue({ ...SAVED, smtp_port: 465 });
    const wrapper = await mounted();
    await field(wrapper, "port").setValue("465");
    await field(wrapper, "to").setValue("team@example.com\noncall@example.com");
    await field(wrapper, "form").trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ smtp_port: 465, to: ["team@example.com", "oncall@example.com"] });
    expect(field(wrapper, "notice").text()).toContain("next email");
    wrapper.unmount();
  });

  it("sends a new password, or null to remove it, and never both", async () => {
    const save = vi.spyOn(emailSettingsClient, "save").mockResolvedValue(SAVED);
    const wrapper = await mounted();
    await field(wrapper, "password").setValue("n3w");
    await field(wrapper, "form").trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenLastCalledWith({ password: "n3w" });
    await field(wrapper, "clear-password").setValue(true);
    await field(wrapper, "form").trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenLastCalledWith({ password: null });
    wrapper.unmount();
  });

  it("shows the refusal and keeps what was typed", async () => {
    vi.spyOn(emailSettingsClient, "save").mockRejectedValue(new Error("Email settings: 'smtp_port' must be a whole number."));
    const wrapper = await mounted();
    await field(wrapper, "server").setValue("smtp.other.com");
    await field(wrapper, "form").trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("whole number");
    expect((field(wrapper, "server").element as HTMLInputElement).value).toBe("smtp.other.com");
    wrapper.unmount();
  });
});
