import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { appConfigClient, type AppConfig } from "../api/AppConfigClient";
import { ConfirmModal } from "@citadel/ui";
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

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
});

beforeEach(() => {
  vi.spyOn(appConfigClient, "get").mockResolvedValue(VIEW);
});
afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = ""; });

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
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    expect(wrapper.findAll(".draft-actions .action-slot")).toHaveLength(2);
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
    await field(wrapper, "save").trigger("click");
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
    await field(wrapper, "session_hours").setValue("5");
    await field(wrapper, "save").trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Session length");
    expect((field(wrapper, "session_hours").element as HTMLInputElement).value).toBe("5");
    wrapper.unmount();
  });

  it("blocks a save on a hidden invalid field, reveals it and keeps the other edits", async () => {
    const save = vi.spyOn(appConfigClient, "save").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await field(wrapper, "session_hours").setValue("4");
    await field(wrapper, "bk_keep").setValue("0");
    await wrapper.get('input[type="search"]').setValue("accounts");
    expect(field(wrapper, "bk_keep").element.closest("fieldset")!.style.display).toBe("none");
    await field(wrapper, "save").trigger("click");
    await flushPromises();
    expect(save).not.toHaveBeenCalled();
    expect((wrapper.get('input[type="search"]').element as HTMLInputElement).value).toBe("");
    expect(field(wrapper, "bk_keep").element.closest("fieldset")!.style.display).not.toBe("none");
    expect(document.activeElement).toBe(field(wrapper, "bk_keep").element);
    expect((field(wrapper, "session_hours").element as HTMLInputElement).value).toBe("4");
    wrapper.unmount();
  });

  it("sends edits made to hidden groups", async () => {
    const save = vi.spyOn(appConfigClient, "save").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await field(wrapper, "bk_keep").setValue("7");
    await wrapper.get('input[type="search"]').setValue("accounts");
    await field(wrapper, "save").trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ backup: { keep: 7 } });
    wrapper.unmount();
  });

  it("confirms before discarding and restores the saved values", async () => {
    const save = vi.spyOn(appConfigClient, "save");
    const wrapper = await mounted();
    await field(wrapper, "session_hours").setValue("4");
    await field(wrapper, "cancel").trigger("click");
    await wrapper.getComponent(ConfirmModal).vm.$emit("confirm");
    await flushPromises();
    expect(save).not.toHaveBeenCalled();
    expect((field(wrapper, "session_hours").element as HTMLInputElement).value).toBe("12");
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
