import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import type { AdminAccount, Role } from "../../api/AdminClient";
import { useAuthStore } from "../../stores/auth";
import AccountDrawer from "./AccountDrawer.vue";

const ALL = ["accounts.manage", "accounts.delete", "roles.assign", "chat.use"];
const role = (id: number, name: string, permissions: string[] = []): Role => ({ id, name, description: null, is_protected: false, permissions, account_count: 0 });
const ROLES = [role(2, "Member"), role(3, "Support"), role(4, "Owner", ["billing.manage"])];

function account(extra: Partial<AdminAccount> = {}): AdminAccount {
  return { id: 2, username: "maria", email: "maria@mail.com", email_verified: true, is_active: true, is_protected: false, created_at: "2026-09-12T10:00:00", roles: [{ id: 2, name: "Member" }, { id: 3, name: "Support" }], ...extra };
}

function show(extra: Record<string, unknown> = {}, permissions = ALL) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = { id: 1, username: "admin", email: "a@b.c", email_verified: true, roles: [], permissions };
  return mount(AccountDrawer, {
    props: { account: account(), roles: ROLES, isSelf: false, busy: false, error: "", notice: "", editing: false, draft: { username: "maria", email: "maria@mail.com", roleIds: [2, 3] }, ...extra },
    global: { plugins: [pinia] },
  });
}

const choice = (w: ReturnType<typeof show>, name: string) => w.findAll(".role-choice").find((l) => l.text() === name)!.get("input");

describe("AccountDrawer", () => {
  beforeEach(() => localStorage.clear());

  it("shows every role, or No roles for an empty set", () => {
    expect(show().findAll(".roles-section .role-name").map((c) => c.text())).toEqual(["Member", "Support"]);
    expect(show({ account: account({ roles: [] }) }).get(".roles-section").text()).toContain("No roles");
  });

  it("stages role choices by ID and keeps what it did not change", async () => {
    const w = show({ editing: true });
    await choice(w, "Support").setValue(false);
    expect(w.emitted("update:draft")![0]).toEqual([{ username: "maria", email: "maria@mail.com", roleIds: [2] }]);
    await w.get('input[type="email"]').setValue("x@y.z");
    expect(w.emitted("update:draft")![1]).toEqual([{ username: "maria", email: "x@y.z", roleIds: [2, 3] }]);
  });

  it("locks roles the actor may not grant, but still allows removing a held one", () => {
    const w = show({ editing: true, account: account({ roles: [{ id: 4, name: "Owner" }] }), draft: { username: "maria", email: "m@x.y", roleIds: [4] } });
    expect(choice(w, "Owner").element.disabled).toBe(false);
    expect(choice(w, "Support").element.disabled).toBe(false);
    expect(show({ editing: true }).findAll(".role-choice").find((l) => l.text() === "Owner")!.get("input").element.disabled).toBe(true);
  });

  it("hides the staged fields the actor may not use", () => {
    const noAssign = show({ editing: true }, ["accounts.manage"]);
    expect(noAssign.find('input[type="email"]').exists()).toBe(true);
    expect(choice(noAssign, "Member").element.disabled).toBe(true);
    const noManage = show({ editing: true }, ["roles.assign"]);
    expect(noManage.find('input[type="email"]').exists()).toBe(false);
    expect(noManage.find(".role-choice").exists()).toBe(true);
  });

  it("asks to disable an active account and to enable a disabled one", async () => {
    const active = show();
    await active.get('input[role="switch"]').setValue(false);
    expect(active.emitted("setActive")![0]).toEqual([false]);
    const off = show({ account: account({ is_active: false }) });
    await off.get('input[role="switch"]').setValue(true);
    expect(off.emitted("setActive")![0]).toEqual([true]);
  });

  it("offers send verification only while the email is unverified", () => {
    expect(show().text()).not.toContain("Send verification");
    expect(show({ account: account({ email_verified: false }) }).text()).toContain("Send verification");
  });

  it("reports delete and send verification", async () => {
    const w = show({ account: account({ email_verified: false }) });
    await w.findAll("button").find((b) => b.text() === "Send verification")!.trigger("click");
    await w.findAll("button").find((b) => b.text() === "Delete user")!.trigger("click");
    expect(w.emitted("sendVerification")).toHaveLength(1);
    expect(w.emitted("remove")).toHaveLength(1);
  });

  it("keeps your own account from being disabled or deleted", () => {
    const w = show({ isSelf: true });
    expect(w.text()).toContain("Your account");
    expect(w.find('input[role="switch"]').exists()).toBe(false);
    expect(w.text()).not.toContain("Delete user");
  });

  it("offers nothing to change on the protected account", () => {
    const w = show({ account: account({ is_protected: true }) });
    expect(w.text()).toContain("protected admin user");
    expect(w.find('input[role="switch"]').exists()).toBe(false);
    expect(w.text()).not.toContain("Delete user");
  });

  it("disables the controls while a call runs and shows the error and notice", () => {
    const w = show({ busy: true, error: "It failed", notice: "Done" });
    expect(w.get(".error").text()).toBe("It failed");
    expect(w.get(".notice").text()).toBe("Done");
    expect(w.findAll("button").every((b) => b.element.disabled)).toBe(true);
  });
});
