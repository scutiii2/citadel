import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { adminClient, type PermissionInfo, type Role } from "../../api/AdminClient";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import ConfirmModal from "./ConfirmModal.vue";
import RolesPanel from "./RolesPanel.vue";

vi.mock("../../api/AdminClient", () => ({
  adminClient: {
    listAccounts: vi.fn(),
    listRoles: vi.fn(),
    listPermissions: vi.fn(),
    createRole: vi.fn(),
    updateRole: vi.fn(),
    deleteRole: vi.fn(),
  },
}));

const client = vi.mocked(adminClient);

// jsdom has no <dialog> methods.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
  HTMLFormElement.prototype.reportValidity ??= function () { return true; };
});

const PERMISSIONS: PermissionInfo[] = [
  { name: "chat.use", description: "Chat with the agent" },
  { name: "roles.manage", description: "Manage accounts" },
];

const ADMIN: Role = { id: 1, name: "Administrator", description: null, is_protected: true, permissions: ["chat.use", "roles.manage"], account_count: 1 };
const MEMBER: Role = { id: 2, name: "Member", description: "Default role", is_protected: false, permissions: ["chat.use"], account_count: 3 };
const OPS: Role = { id: 3, name: "Ops", description: null, is_protected: false, permissions: [], account_count: 0 };

async function panel() {
  const wrapper = mount(RolesPanel, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
type Panel = Awaited<ReturnType<typeof panel>>;

const rowFor = (wrapper: Panel, name: string) => wrapper.findAll("tbody tr").find((r) => r.text().includes(name))!;
const body = (wrapper: Panel) => wrapper.find(".role-body");
const open = async (wrapper: Panel, name: string) => { await rowFor(wrapper, name).get(".admin-row-button").trigger("click"); await flushPromises(); };
const ask = (wrapper: Panel, title: string) => wrapper.findAllComponents(ConfirmModal).find((c) => c.props("title") === title)!;
const edit = async (wrapper: Panel) => { await wrapper.get('[data-test="edit"]').trigger("click"); await flushPromises(); };
const flip = (wrapper: Panel, name: string, on: boolean) => body(wrapper).get(`input[aria-label="${name}"]`).setValue(on);
const checked = (wrapper: Panel, name: string) => (body(wrapper).get(`input[aria-label="${name}"]`).element as HTMLInputElement).checked;
async function save(wrapper: Panel) {
  await wrapper.get('[data-test="save-role"]').trigger("click");
  await ask(wrapper, "Save changes?").vm.$emit("confirm");
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "admin@mail.com", email_verified: true, roles: ["Administrator"], permissions: ["roles.view", "roles.manage", "chat.use", "tools.view", "accounts.view"] };
  client.listRoles.mockResolvedValue([ADMIN, MEMBER, OPS]);
  client.listPermissions.mockResolvedValue(PERMISSIONS);
});
afterEach(() => { document.body.innerHTML = ""; });

describe("RolesPanel", () => {
  it("lists the roles with description and account count, searchable", async () => {
    const wrapper = await panel();
    expect(rowFor(wrapper, "Administrator").text()).toContain("protected");
    expect(rowFor(wrapper, "Member").text()).toContain("Default role");
    expect(rowFor(wrapper, "Member").findAll("td")[0]!.text()).toBe("3");
    expect(wrapper.get("thead").text()).toContain("Users");
    await wrapper.get('input[type="search"]').setValue("default");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    await wrapper.get('input[type="search"]').setValue("zzz");
    expect(wrapper.text()).toContain("No roles match your search.");
    wrapper.unmount();
  });

  it("shows the error with a retry when the roles cannot be read", async () => {
    client.listRoles.mockRejectedValueOnce(new ApiError(500, "boom"));
    const wrapper = await panel();
    expect(wrapper.get("[role=alert]").text()).toContain("boom");
    await wrapper.get("[role=alert] button").trigger("click");
    await flushPromises();
    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
    wrapper.unmount();
  });

  it("opens a role read-only in the drawer", async () => {
    const wrapper = await panel();
    await open(wrapper, "Member");
    expect(body(wrapper).attributes("aria-label")).toBe("Role Member");
    expect(body(wrapper).get('input[aria-label="chat.use"]').attributes("disabled")).toBeDefined();
    expect(body(wrapper).text()).toContain("Default role");
    wrapper.unmount();
  });

  it("saves a permission change after validation and the save confirmation", async () => {
    client.updateRole.mockResolvedValue({ ...MEMBER, permissions: ["chat.use", "roles.manage"] });
    const wrapper = await panel();
    await open(wrapper, "Member");
    await edit(wrapper);
    await flip(wrapper, "roles.manage", true);
    await wrapper.get('[data-test="save-role"]').trigger("click");
    expect(client.updateRole).not.toHaveBeenCalled();
    await ask(wrapper, "Save changes?").vm.$emit("confirm");
    await flushPromises();
    expect(client.updateRole).toHaveBeenCalledWith(2, { permissions: ["chat.use", "roles.manage"] });
    expect(body(wrapper).get(".chip.saved").text()).toBe("Saved");
    expect(wrapper.find("#role-editor").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps hidden permission edits in the saved payload", async () => {
    client.updateRole.mockResolvedValue({ ...MEMBER, permissions: [] });
    const wrapper = await panel();
    await open(wrapper, "Member");
    await edit(wrapper);
    await flip(wrapper, "chat.use", false);
    await body(wrapper).get('input[type="search"]').setValue("manage");
    expect(body(wrapper).find('input[aria-label="chat.use"]').exists()).toBe(false);
    await save(wrapper);
    expect(client.updateRole).toHaveBeenCalledWith(2, { permissions: [] });
    wrapper.unmount();
  });

  it("keeps the draft and shows the server's refusal when a save fails", async () => {
    client.updateRole.mockRejectedValue(new ApiError(409, "That would remove your own admin access"));
    const wrapper = await panel();
    await open(wrapper, "Member");
    await edit(wrapper);
    await flip(wrapper, "chat.use", false);
    await save(wrapper);
    expect(body(wrapper).get(".error").text()).toContain("own admin access");
    expect(checked(wrapper, "chat.use")).toBe(false);
    expect(wrapper.find("#role-editor").exists()).toBe(true);
    wrapper.unmount();
  });

  it("drops the draft on cancel without any write", async () => {
    const wrapper = await panel();
    await open(wrapper, "Member");
    await edit(wrapper);
    await flip(wrapper, "chat.use", false);
    await wrapper.get('[data-test="cancel-edit"]').trigger("click");
    await ask(wrapper, "Discard changes?").vm.$emit("confirm");
    await flushPromises();
    expect(client.updateRole).not.toHaveBeenCalled();
    expect(checked(wrapper, "chat.use")).toBe(true);
    wrapper.unmount();
  });

  it("re-reads the logged-in account only when it holds the changed role", async () => {
    const auth = useAuthStore();
    const refresh = vi.spyOn(auth, "refresh").mockResolvedValue();
    client.updateRole.mockResolvedValue({ ...MEMBER, description: "Everyone" });
    const wrapper = await panel();
    await open(wrapper, "Member");
    await edit(wrapper);
    await body(wrapper).get('input[maxlength="255"]').setValue("Everyone");
    await save(wrapper);
    expect(client.updateRole).toHaveBeenCalledWith(2, { description: "Everyone" });
    expect(refresh).not.toHaveBeenCalled();

    client.updateRole.mockResolvedValue({ ...OPS, description: "Held" });
    auth.account!.roles = ["Ops"];
    await wrapper.get('dialog[aria-label="Role Member"] button[aria-label="Close"]').trigger("click");
    await open(wrapper, "Ops");
    await edit(wrapper);
    await body(wrapper).get('input[maxlength="255"]').setValue("Held");
    await save(wrapper);
    expect(refresh).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("keeps the protected role read-only", async () => {
    const wrapper = await panel();
    await open(wrapper, "Administrator");
    expect(wrapper.find('[data-test="edit"]').exists()).toBe(true);
    await edit(wrapper);
    expect(body(wrapper).get('input[aria-label="chat.use"]').attributes("disabled")).toBeDefined();
    expect(body(wrapper).get('input[maxlength="80"]').attributes("disabled")).toBeDefined();
    expect(body(wrapper).text()).not.toContain("Delete role");
    wrapper.unmount();
  });

  it("creates a role in the drawer, keeps the list sorted and opens the new role", async () => {
    client.createRole.mockResolvedValue({ id: 4, name: "Auditors", description: null, is_protected: false, permissions: [], account_count: 0 });
    const wrapper = await panel();
    await wrapper.get('[data-test="new-role"]').trigger("click");
    await wrapper.get('#role-create input[maxlength="80"]').setValue(" Auditors ");
    await wrapper.get('[data-test="create-role"]').trigger("click");
    await ask(wrapper, "Save changes?").vm.$emit("confirm");
    await flushPromises();
    expect(client.createRole).toHaveBeenCalledWith("Auditors", null);
    expect(wrapper.findAll("tbody th .admin-row-button").map((b) => b.text())).toEqual(["Administrator", "Auditors", "Member", "Ops"]);
    expect(body(wrapper).attributes("aria-label")).toBe("Role Auditors");
    wrapper.unmount();
  });

  it("keeps the create drawer open and shows why it failed", async () => {
    client.createRole.mockRejectedValue(new ApiError(409, "Role name 'Ops' is already in use"));
    const wrapper = await panel();
    await wrapper.get('[data-test="new-role"]').trigger("click");
    await wrapper.get('#role-create input[maxlength="80"]').setValue("Ops");
    await wrapper.get('[data-test="create-role"]').trigger("click");
    await ask(wrapper, "Save changes?").vm.$emit("confirm");
    await flushPromises();
    expect(wrapper.get("#role-create .error").text()).toContain("already in use");
    expect((wrapper.get('#role-create input[maxlength="80"]').element as HTMLInputElement).value).toBe("Ops");
    wrapper.unmount();
  });

  it("asks before deleting and types the name when accounts hold the role", async () => {
    client.deleteRole.mockResolvedValue(undefined);
    const wrapper = await panel();
    await open(wrapper, "Member");
    await body(wrapper).findAll("button").find((b) => b.text() === "Delete role")!.trigger("click");
    const dialog = ask(wrapper, "Delete role");
    expect(dialog.props("message")).toBe("Delete role 'Member'? It is removed from 3 accounts.");
    expect(dialog.props("requireText")).toBe("Member");
    expect(client.deleteRole).not.toHaveBeenCalled();
    await dialog.vm.$emit("confirm");
    await flushPromises();
    expect(client.deleteRole).toHaveBeenCalledWith(2);
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
    expect(body(wrapper).exists()).toBe(false);
    wrapper.unmount();
  });

  it("asks for no typing when no account holds the role, and shows a refused delete", async () => {
    client.deleteRole.mockRejectedValue(new ApiError(409, "In use"));
    const wrapper = await panel();
    await open(wrapper, "Ops");
    await body(wrapper).findAll("button").find((b) => b.text() === "Delete role")!.trigger("click");
    expect(ask(wrapper, "Delete role").props("requireText")).toBe("");
    await ask(wrapper, "Delete role").vm.$emit("confirm");
    await flushPromises();
    expect(body(wrapper).get(".error").text()).toContain("In use");
    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
    wrapper.unmount();
  });

  it("guards a route change while a draft is unsaved", async () => {
    const wrapper = await panel();
    await open(wrapper, "Member");
    await edit(wrapper);
    await flip(wrapper, "chat.use", false);
    const vm = wrapper.vm as unknown as { confirmDiscard: () => Promise<boolean> };
    const answer = vm.confirmDiscard();
    await flushPromises();
    const dialog = ask(wrapper, "Discard unsaved changes?");
    expect(dialog.props("open")).toBe(true);
    await dialog.vm.$emit("close");
    expect(await answer).toBe(false);
    expect(checked(wrapper, "chat.use")).toBe(false);
    const second = vm.confirmDiscard();
    await flushPromises();
    await ask(wrapper, "Discard unsaved changes?").vm.$emit("confirm");
    expect(await second).toBe(true);
    wrapper.unmount();
  });

  it("warns on page unload only with unsaved edits", async () => {
    const wrapper = await panel();
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    await open(wrapper, "Member");
    await edit(wrapper);
    await flip(wrapper, "chat.use", false);
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    wrapper.unmount();
  });

  it("loads only the affected accounts on demand", async () => {
    client.listAccounts.mockResolvedValue([
      { id: 2, username: "member", email: "m@example.com", is_active: true, email_verified: true, is_protected: false, created_at: "", roles: [{ id: 2, name: "Member" }] },
      { id: 3, username: "other", email: "o@example.com", is_active: true, email_verified: true, is_protected: false, created_at: "", roles: [] },
    ]);
    const wrapper = await panel();
    expect(client.listAccounts).not.toHaveBeenCalled();
    await open(wrapper, "Member");
    await body(wrapper).findAll("button").find((b) => b.text() === "View affected accounts")!.trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".affected-accounts li")).toHaveLength(1);
    expect(wrapper.find(".affected-accounts").text()).toContain("m@example.com");
    expect(wrapper.find(".affected-accounts").text()).not.toContain("o@example.com");
    wrapper.unmount();
  });

  it("shows custom permissions in the role drawer", async () => {
    client.listPermissions.mockResolvedValue([...PERMISSIONS, { name: "custom.action", description: "Run a custom action" }]);
    const wrapper = await panel();
    await open(wrapper, "Member");
    expect(body(wrapper).text()).toContain("custom.action");
    expect(body(wrapper).text()).toContain("Run a custom action");
    wrapper.unmount();
  });
});
