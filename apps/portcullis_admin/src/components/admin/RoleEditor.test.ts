import { useAuthStore } from "../../stores/auth";
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import type { PermissionInfo, Role } from "../../api/AdminClient";
import RoleEditor from "./RoleEditor.vue";

const PERMISSIONS: PermissionInfo[] = [
  { name: "chat.use", description: "Chat with the agent" },
  { name: "tools.view", description: "Run mcp_server tools" },
  { name: "roles.manage", description: null },
];

const MEMBER: Role = { id: 2, name: "Member", description: "Default role", is_protected: false, permissions: ["chat.use", "tools.view"], account_count: 2 };
const ADMIN: Role = { id: 1, name: "Administrator", description: null, is_protected: true, permissions: ["chat.use", "tools.view", "roles.manage"], account_count: 1 };
const NO_AFFECTED = { loading: false, error: "", accounts: null };

type Props = { busy?: boolean; error?: string; saved?: boolean; editing?: boolean; affected?: typeof NO_AFFECTED | { loading: boolean; error: string; accounts: never[] } };
function editor(role: Role = MEMBER, props: Props = {}) {
  return mount(RoleEditor, { props: { role, permissions: PERMISSIONS, busy: false, error: "", editing: false, affected: NO_AFFECTED, ...props } });
}

const switchFor = (wrapper: ReturnType<typeof editor>, name: string) => wrapper.get(`input[aria-label="${name}"]`);
const isOn = (wrapper: ReturnType<typeof editor>, name: string) => (switchFor(wrapper, name).element as HTMLInputElement).checked;
type Exposed = { dirty: boolean; valid: boolean; changes: unknown; revert: () => void };
const exposed = (wrapper: ReturnType<typeof editor>) => wrapper.vm as unknown as Exposed;

beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "a@example.com", email_verified: true, roles: [], permissions: ["roles.manage", "chat.use", "tools.view", "accounts.view"] };
});

describe("RoleEditor", () => {
  it("shows the role, its description and its account count", () => {
    const text = editor().text();
    expect(text).toContain("Default role");
    expect(text).toContain("2 users");
    expect(editor({ ...MEMBER, account_count: 1 }).text()).toContain("1 user");
  });

  it("shows a switch per permission, on for the ones the role holds, locked until editing", () => {
    const wrapper = editor();
    expect(wrapper.findAll('input[role="switch"]')).toHaveLength(3);
    expect(isOn(wrapper, "chat.use")).toBe(true);
    expect(isOn(wrapper, "roles.manage")).toBe(false);
    expect(wrapper.text()).toContain("Run mcp_server tools");
    expect(switchFor(wrapper, "chat.use").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).not.toContain("Changes are a draft");
  });

  it("stages permission changes in a draft the parent reads", async () => {
    const wrapper = editor(MEMBER, { editing: true });
    expect(wrapper.text()).toContain("Changes are a draft until you save.");
    await switchFor(wrapper, "roles.manage").setValue(true);
    await switchFor(wrapper, "chat.use").setValue(false);
    expect(exposed(wrapper).dirty).toBe(true);
    expect(exposed(wrapper).changes).toEqual({ permissions: ["roles.manage", "tools.view"] });
    expect(wrapper.emitted("dirty")).toEqual([[true]]);
  });

  it("changes only the fields that differ and can clear the description", async () => {
    const wrapper = editor(MEMBER, { editing: true });
    const inputs = wrapper.findAll("#role-editor input");
    await inputs[1]!.setValue("New text");
    expect(exposed(wrapper).changes).toEqual({ description: "New text" });
    await inputs[1]!.setValue("");
    expect(exposed(wrapper).changes).toEqual({ description: "" });
    await inputs[1]!.setValue("Default role");
    expect(exposed(wrapper).dirty).toBe(false);
  });

  it("is invalid without a name", async () => {
    const wrapper = editor(MEMBER, { editing: true });
    await wrapper.get("#role-editor input").setValue("   ");
    expect(exposed(wrapper).valid).toBe(false);
  });

  it("locks the Administrator role: no deleting, no renaming, no permission changes", () => {
    const wrapper = editor(ADMIN, { editing: true });
    expect(wrapper.text()).toContain("always holds every permission");
    expect(wrapper.text()).not.toContain("Delete role");
    for (const input of wrapper.findAll('input[role="switch"]')) expect(input.attributes("disabled")).toBeDefined();
    expect(wrapper.get("#role-editor input").attributes("disabled")).toBeDefined();
  });

  it("never sends a name for the protected role", async () => {
    const wrapper = editor(ADMIN, { editing: true });
    await wrapper.findAll("#role-editor input")[1]!.setValue("Everything");
    expect(exposed(wrapper).changes).toEqual({ description: "Everything" });
  });

  it("asks to delete the role, and offers it only outside editing", async () => {
    const wrapper = editor();
    await wrapper.findAll("button").find((b) => b.text() === "Delete role")!.trigger("click");
    expect(wrapper.emitted("remove")).toHaveLength(1);
    expect(editor(MEMBER, { editing: true }).text()).not.toContain("Delete role");
  });

  it("disables the controls while a call runs", () => {
    const wrapper = editor(MEMBER, { busy: true, editing: true });
    for (const input of wrapper.findAll('input[role="switch"]')) expect(input.attributes("disabled")).toBeDefined();
    expect(wrapper.findAll("button").every((b) => b.attributes("disabled") !== undefined)).toBe(true);
  });

  it("shows the error and the Saved chip only without an error", () => {
    expect(editor(MEMBER, { error: "That would remove your own admin access" }).get(".error").text()).toBe("That would remove your own admin access");
    expect(editor(MEMBER, { saved: true }).get(".action-message.ok").text()).toBe("Saved");
    expect(editor(MEMBER, { saved: true, error: "boom" }).find(".action-message.ok").exists()).toBe(false);
  });

  it("shows roles read-only without roles.manage", () => {
    useAuthStore().account!.permissions = ["roles.view"];
    const wrapper = editor(MEMBER, { editing: true });
    expect(wrapper.findAll("input[type=checkbox]").every((input) => (input.element as HTMLInputElement).disabled)).toBe(true);
    expect(wrapper.find(".danger-zone").exists()).toBe(false);
  });

  it("groups permissions and searches by label, key, or description without losing the draft", async () => {
    const wrapper = editor(MEMBER, { editing: true });
    expect(wrapper.get('section[aria-label="Chat & files"]').text()).toContain("Use chat");
    expect(wrapper.get('section[aria-label="Accounts & access"]').text()).toContain("0 of 1 enabled");
    await switchFor(wrapper, "chat.use").setValue(false);
    await wrapper.get('input[aria-label="Find a permission"]').setValue("browse");
    expect(wrapper.findAll('input[role="switch"]')).toHaveLength(1);
    await wrapper.get('input[aria-label="Find a permission"]').setValue("mcp_server");
    expect(switchFor(wrapper, "tools.view").attributes("aria-label")).toBe("tools.view");
    await wrapper.get('input[aria-label="Find a permission"]').setValue("no matches");
    expect(wrapper.text()).toContain("No permissions match your search.");
    await wrapper.get('input[aria-label="Find a permission"]').setValue("");
    expect(isOn(wrapper, "chat.use")).toBe(false);
    expect(exposed(wrapper).changes).toEqual({ permissions: ["tools.view"] });
  });

  it("resets the draft when the server supplies the saved role", async () => {
    const wrapper = editor(MEMBER, { editing: true });
    await switchFor(wrapper, "roles.manage").setValue(true);
    await wrapper.setProps({ role: { ...MEMBER, permissions: [...MEMBER.permissions, "roles.manage"] } });
    expect(isOn(wrapper, "roles.manage")).toBe(true);
    expect(exposed(wrapper).dirty).toBe(false);
  });

  it("shows permissions added by the server even when their group is not yet known", async () => {
    const wrapper = editor();
    await wrapper.setProps({ permissions: [...PERMISSIONS, { name: "new.permission", description: "Future feature" }] });
    expect(wrapper.get('section[aria-label="Other permissions"]').text()).toContain("new.permission");
    expect(switchFor(wrapper, "new.permission").attributes("disabled")).toBeDefined();
  });

  it("reverts details and permissions together", async () => {
    const wrapper = editor(MEMBER, { editing: true });
    await wrapper.findAll("#role-editor input")[1]!.setValue("Changed");
    await switchFor(wrapper, "chat.use").setValue(false);
    exposed(wrapper).revert();
    await wrapper.vm.$nextTick();
    expect(exposed(wrapper).dirty).toBe(false);
    expect(isOn(wrapper, "chat.use")).toBe(true);
  });
});
