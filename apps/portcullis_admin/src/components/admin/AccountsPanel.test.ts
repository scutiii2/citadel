import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { adminClient, type AdminAccount, type Role } from "../../api/AdminClient";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import AccountsPanel from "./AccountsPanel.vue";
import ConfirmModal from "./ConfirmModal.vue";

vi.mock("../../api/AdminClient", () => ({
  adminClient: {
    listAccounts: vi.fn(),
    listRoles: vi.fn(),
    updateAccount: vi.fn(),
    deleteAccount: vi.fn(),
    assignRole: vi.fn(),
    removeRole: vi.fn(),
    sendVerification: vi.fn(),
  },
}));

const client = vi.mocked(adminClient);

// jsdom has no <dialog> methods.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
  HTMLFormElement.prototype.reportValidity ??= function () { return true; };
});

const role = (id: number, name: string, protectedRole = false): Role => ({ id, name, description: null, is_protected: protectedRole, permissions: [], account_count: 1 });
const ROLES: Role[] = [role(1, "Administrator", true), role(2, "Member"), role(3, "Support"), role(4, "Auditor")];

function account(id: number, username: string, extra: Partial<AdminAccount> = {}): AdminAccount {
  return {
    id, username, email: `${username}@mail.com`, email_verified: true, is_active: true, is_protected: false,
    created_at: "2026-09-12T10:00:00", roles: [{ id: 2, name: "Member" }], ...extra,
  };
}

const ADMIN = account(1, "admin", { is_protected: true, roles: [{ id: 1, name: "Administrator" }] });
const MARIA = account(2, "maria", { email_verified: false });
const LI = account(3, "li", { is_active: false, roles: [] });
const DUO = account(4, "duo", { roles: [{ id: 2, name: "Member" }, { id: 3, name: "Support" }] });

async function panel(filters?: { q: string; status: "all" | "unverified" | "disabled" }) {
  const wrapper = mount(AccountsPanel, { props: { filters }, attachTo: document.body, global: { plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] })] } });
  await flushPromises();
  return wrapper;
}

type Panel = Awaited<ReturnType<typeof panel>>;

const rowFor = (wrapper: Panel, name: string) => wrapper.findAll("tbody tr").find((r) => r.text().includes(name))!;
const drawer = (wrapper: Panel) => wrapper.find(".account-body");
const ask = (wrapper: Panel, title: string) => wrapper.findAllComponents(ConfirmModal).find((c) => c.props("title") === title)!;
const open = async (wrapper: Panel, name: string) => { await rowFor(wrapper, name).get(".admin-row-button").trigger("click"); await flushPromises(); };
const clickIn = (root: { findAll: Panel["findAll"] }, label: string) => root.findAll("button").find((b) => b.text() === label)!.trigger("click");

async function edit(wrapper: Panel) {
  await wrapper.get('[data-test="edit"]').trigger("click");
  await flushPromises();
}
async function save(wrapper: Panel) {
  await wrapper.get('[data-test="save-account"]').trigger("click");
  await ask(wrapper, "Save changes?").vm.$emit("confirm");
  await flushPromises();
}
const checkbox = (wrapper: Panel, name: string) => wrapper.findAll(".role-choice").find((l) => l.text() === name)!.get("input");

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "admin@mail.com", email_verified: true, roles: [], permissions: ["accounts.view", "accounts.manage", "accounts.delete", "roles.view", "roles.manage", "roles.assign", "invites.manage", "chat.use", "tools.view"] };
  client.listAccounts.mockResolvedValue([ADMIN, MARIA, LI, DUO]);
  client.listRoles.mockResolvedValue(ROLES);
});

afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ""; });

describe("AccountsPanel roster", () => {
  it("lists accounts with their roles and status", async () => {
    const wrapper = await panel();
    expect(wrapper.findAll("tbody tr")).toHaveLength(4);
    expect(rowFor(wrapper, "admin").text()).toContain("protected");
    expect(rowFor(wrapper, "admin").text()).toContain("you");
    expect(rowFor(wrapper, "maria").text()).toContain("unverified");
    expect(rowFor(wrapper, "li").text()).toContain("disabled");
    expect(rowFor(wrapper, "li").text()).toContain("No roles");
    expect(rowFor(wrapper, "duo").text()).toContain("Support");
    wrapper.unmount();
  });

  it("searches username, email and any assigned role locally", async () => {
    const wrapper = await panel();
    await wrapper.get('input[type="search"]').setValue("support");
    expect(wrapper.findAll("tbody tr").map((r) => r.text())).toEqual([expect.stringContaining("duo")]);
    await wrapper.get('input[type="search"]').setValue("MARIA@mail");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    await wrapper.get('input[type="search"]').setValue("zzz");
    expect(wrapper.text()).toContain("No users match your search.");
    expect(client.listAccounts).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("filters by status through the existing roster request", async () => {
    const wrapper = await panel();
    client.listAccounts.mockResolvedValue([LI]);
    await wrapper.findAll(".filters button").find((b) => b.text().startsWith("Disabled"))!.trigger("click");
    await flushPromises();
    expect(client.listAccounts).toHaveBeenLastCalledWith({ status: "disabled" });
    expect(wrapper.emitted("filter")!.at(-1)).toEqual([{ q: "", status: "disabled" }]);
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    wrapper.unmount();
  });

  it("loads bookmark filters and follows updates from browser navigation", async () => {
    const wrapper = await panel({ q: "mar", status: "unverified" });
    expect(client.listAccounts).toHaveBeenCalledWith({ status: "unverified" });
    expect((wrapper.get('input[type="search"]').element as HTMLInputElement).value).toBe("mar");
    await wrapper.setProps({ filters: { q: "", status: "all" } });
    await flushPromises();
    expect(client.listAccounts).toHaveBeenLastCalledWith({ status: "all" });
    wrapper.unmount();
  });

  it("ignores a slow answer to an older status", async () => {
    let releaseOld: (rows: AdminAccount[]) => void = () => {};
    const wrapper = await panel();
    client.listAccounts.mockReturnValueOnce(new Promise((resolve) => { releaseOld = resolve; }));
    client.listAccounts.mockResolvedValueOnce([LI]);
    const buttons = wrapper.findAll(".filters button");
    await buttons.find((b) => b.text().startsWith("Unverified"))!.trigger("click");
    await buttons.find((b) => b.text().startsWith("Disabled"))!.trigger("click");
    await flushPromises();
    releaseOld([MARIA]);
    await flushPromises();
    expect(wrapper.findAll("tbody tr").map((r) => r.text())).toEqual([expect.stringContaining("li")]);
    wrapper.unmount();
  });

  it("shows the error with a retry when the roster cannot be read", async () => {
    client.listAccounts.mockRejectedValue(new ApiError(500, "boom"));
    const wrapper = await panel();
    expect(wrapper.get("[role=alert]").text()).toContain("boom");
    client.listAccounts.mockResolvedValue([ADMIN]);
    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    wrapper.unmount();
  });
});

describe("AccountsPanel drawer", () => {
  it("opens the drawer for the row and closes it again", async () => {
    const wrapper = await panel();
    expect(drawer(wrapper).exists()).toBe(false);
    await open(wrapper, "maria");
    expect(wrapper.get('dialog[aria-label="User maria"]').attributes("open")).toBeDefined();
    expect(drawer(wrapper).text()).toContain("maria@mail.com");
    await wrapper.get('dialog[aria-label="User maria"] button[aria-label="Close"]').trigger("click");
    expect(drawer(wrapper).exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows every assigned role, and No roles for an empty set", async () => {
    const wrapper = await panel();
    await open(wrapper, "duo");
    expect(drawer(wrapper).findAll(".roles-section .role-name").map((c) => c.text())).toEqual(["Member", "Support"]);
    await wrapper.get('dialog[aria-label="User duo"] button[aria-label="Close"]').trigger("click");
    await open(wrapper, "li");
    expect(drawer(wrapper).find(".roles-section").text()).toContain("No roles");
    wrapper.unmount();
  });

  it("keeps the protected account read-only", async () => {
    const wrapper = await panel();
    await open(wrapper, "admin");
    expect(wrapper.find('[data-test="edit"]').exists()).toBe(false);
    expect(drawer(wrapper).text()).toContain("protected admin user");
    expect(drawer(wrapper).find('input[role="switch"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("drops pending edits on discard without any write", async () => {
    const wrapper = await panel();
    await open(wrapper, "maria");
    await edit(wrapper);
    await wrapper.get('input[type="email"]').setValue("other@mail.com");
    await checkbox(wrapper, "Auditor").setValue(true);
    await wrapper.get('[data-test="cancel-edit"]').trigger("click");
    await ask(wrapper, "Discard changes?").vm.$emit("confirm");
    await flushPromises();
    expect(client.updateAccount).not.toHaveBeenCalled();
    expect(client.assignRole).not.toHaveBeenCalled();
    expect(drawer(wrapper).text()).toContain("maria@mail.com");
    expect(wrapper.find("#account-editor").exists()).toBe(false);
    wrapper.unmount();
  });

  it("saves profile first, then additions, then removals, by role ID", async () => {
    const calls: string[] = [];
    client.updateAccount.mockImplementation(async (_id, changes) => { calls.push(`patch ${JSON.stringify(changes)}`); return { ...MARIA, email: "new@mail.com" }; });
    client.assignRole.mockImplementation(async (_id, roleId) => { calls.push(`add ${roleId}`); return { ...MARIA, email: "new@mail.com", roles: [{ id: 2, name: "Member" }, { id: roleId, name: "Auditor" }] }; });
    client.removeRole.mockImplementation(async (_id, roleId) => { calls.push(`remove ${roleId}`); return { ...MARIA, email: "new@mail.com", roles: [{ id: 4, name: "Auditor" }] }; });
    const wrapper = await panel();
    await open(wrapper, "maria");
    await edit(wrapper);
    await wrapper.get('input[type="email"]').setValue("new@mail.com");
    await checkbox(wrapper, "Auditor").setValue(true);
    await checkbox(wrapper, "Member").setValue(false);
    await save(wrapper);
    expect(calls).toEqual(['patch {"email":"new@mail.com"}', "add 4", "remove 2"]);
    expect(rowFor(wrapper, "maria").text()).toContain("Auditor");
    expect(rowFor(wrapper, "maria").text()).not.toContain("Member");
    expect(wrapper.find("#account-editor").exists()).toBe(false);
    expect(wrapper.emitted("changed")).toHaveLength(1);
    wrapper.unmount();
  });

  it("retries only the outstanding part after one of two role calls succeeds", async () => {
    // Support was granted elsewhere after editing began: it was never staged, so it must survive.
    const edited = { ...DUO, email: "new@mail.com" };
    client.updateAccount.mockResolvedValue(edited);
    client.assignRole.mockResolvedValueOnce({ ...edited, roles: [...edited.roles, { id: 4, name: "Auditor" }] });
    client.removeRole.mockRejectedValueOnce(new ApiError(503, "unavailable"));
    const wrapper = await panel();
    await open(wrapper, "duo");
    await edit(wrapper);
    await wrapper.get('input[type="email"]').setValue("new@mail.com");
    await checkbox(wrapper, "Auditor").setValue(true);
    await checkbox(wrapper, "Member").setValue(false);
    await save(wrapper);
    expect(client.updateAccount).toHaveBeenCalledTimes(1);
    expect(client.assignRole).toHaveBeenCalledTimes(1);
    expect(client.removeRole).toHaveBeenCalledTimes(1);
    expect(drawer(wrapper).get(".error").text()).toContain("removing Member");
    expect(drawer(wrapper).get(".error").text()).toContain("unavailable");
    // The confirmed parts show in the roster and the draft is kept for the retry.
    expect(rowFor(wrapper, "duo").text()).toContain("Auditor");
    expect(checkbox(wrapper, "Member").element.checked).toBe(false);
    expect(wrapper.find("#account-editor").exists()).toBe(true);

    const fresh = { ...edited, roles: [{ id: 2, name: "Member" }, { id: 3, name: "Support" }, { id: 4, name: "Auditor" }, { id: 1, name: "Administrator" }] };
    client.listAccounts.mockResolvedValueOnce([ADMIN, MARIA, LI, fresh]);
    client.removeRole.mockResolvedValueOnce({ ...fresh, roles: fresh.roles.filter((r) => r.id !== 2) });
    await save(wrapper);
    expect(client.updateAccount).toHaveBeenCalledTimes(1);
    expect(client.assignRole).toHaveBeenCalledTimes(1);
    expect(client.removeRole).toHaveBeenCalledTimes(2);
    expect(client.removeRole).toHaveBeenLastCalledWith(4, 2);
    expect(rowFor(wrapper, "duo").text()).toContain("Administrator");
    expect(rowFor(wrapper, "duo").text()).toContain("Support");
    expect(wrapper.find("#account-editor").exists()).toBe(false);
    wrapper.unmount();
  });

  it("refreshes the signed-in account after a self change, even on a partial save", async () => {
    const auth = useAuthStore();
    auth.account = { ...auth.account!, id: 2 };
    const refresh = vi.spyOn(auth, "refresh").mockResolvedValue(undefined as never);
    client.assignRole.mockResolvedValueOnce({ ...MARIA, roles: [...MARIA.roles, { id: 3, name: "Support" }] });
    client.removeRole.mockRejectedValueOnce(new ApiError(500, "no"));
    const wrapper = await panel();
    await open(wrapper, "maria");
    await edit(wrapper);
    await checkbox(wrapper, "Support").setValue(true);
    await checkbox(wrapper, "Member").setValue(false);
    await save(wrapper);
    expect(refresh).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("asks before disabling and does nothing when the question is cancelled", async () => {
    const wrapper = await panel();
    await open(wrapper, "maria");
    const toggle = drawer(wrapper).get('input[role="switch"]');
    await toggle.setValue(!(toggle.element as HTMLInputElement).checked);
    expect(ask(wrapper, "Disable user").props("message")).toContain("Disable 'maria'?");
    await ask(wrapper, "Disable user").vm.$emit("close");
    expect(wrapper.findAllComponents(ConfirmModal).some((c) => c.props("open"))).toBe(false);
    expect(client.updateAccount).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("disables an account once confirmed and enables one without asking", async () => {
    client.updateAccount.mockResolvedValueOnce({ ...MARIA, is_active: false });
    const wrapper = await panel();
    await open(wrapper, "maria");
    const toggle = drawer(wrapper).get('input[role="switch"]');
    await toggle.setValue(false);
    await ask(wrapper, "Disable user").vm.$emit("confirm");
    await flushPromises();
    expect(client.updateAccount).toHaveBeenCalledWith(2, { is_active: false });
    expect(rowFor(wrapper, "maria").text()).toContain("disabled");

    client.updateAccount.mockResolvedValueOnce({ ...MARIA, is_active: true });
    await drawer(wrapper).get('input[role="switch"]').setValue(true);
    await flushPromises();
    expect(client.updateAccount).toHaveBeenLastCalledWith(2, { is_active: true });
    wrapper.unmount();
  });

  it("deletes an account once confirmed, then closes the drawer", async () => {
    client.deleteAccount.mockResolvedValue(undefined);
    const wrapper = await panel();
    await open(wrapper, "maria");
    await clickIn(drawer(wrapper), "Delete user");
    expect(ask(wrapper, "Delete user").props("requireText")).toBe("maria");
    await ask(wrapper, "Delete user").vm.$emit("confirm");
    await flushPromises();
    expect(client.deleteAccount).toHaveBeenCalledWith(2);
    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
    expect(drawer(wrapper).exists()).toBe(false);
    wrapper.unmount();
  });

  it("sends a verification email and says so", async () => {
    client.sendVerification.mockResolvedValue({ sent: true });
    const wrapper = await panel();
    await open(wrapper, "maria");
    await clickIn(drawer(wrapper), "Send verification");
    await flushPromises();
    expect(client.sendVerification).toHaveBeenCalledWith(2);
    expect(drawer(wrapper).text()).toContain("Verification email sent to maria@mail.com.");
    wrapper.unmount();
  });

  it("keeps the failed profile edit retryable in the open drawer", async () => {
    client.updateAccount.mockRejectedValue(new ApiError(409, "Email 'x@y.z' is already in use"));
    const wrapper = await panel();
    await open(wrapper, "maria");
    await edit(wrapper);
    await wrapper.get('input[type="email"]').setValue("x@y.z");
    await save(wrapper);
    expect(drawer(wrapper).get(".error").text()).toContain("already in use");
    expect((wrapper.get('input[type="email"]').element as HTMLInputElement).value).toBe("x@y.z");
    expect(rowFor(wrapper, "maria").text()).toContain("maria@mail.com");
    expect(wrapper.emitted("changed")).toBeUndefined();
    wrapper.unmount();
  });
});
