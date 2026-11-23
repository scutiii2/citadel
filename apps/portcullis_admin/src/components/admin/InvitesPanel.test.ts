import { flushPromises, mount } from "@vue/test-utils";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { adminClient, type Invite } from "../../api/AdminClient";
import { ApiError } from "../../api/http";
import ConfirmModal from "./ConfirmModal.vue";
import InvitesPanel from "./InvitesPanel.vue";

vi.mock("../../api/AdminClient", () => ({
  adminClient: { listInvites: vi.fn(), inviteEmailStatus: vi.fn(), createInvite: vi.fn(), revokeInvite: vi.fn() },
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
});

const INVITE: Invite = {
  id: 5,
  invitee_email: "new@mail.com",
  delivery_method: "email",
  created_at: "2026-10-05T09:00:00",
  expires_at: "2026-10-05T09:15:00",
};

const CREATED: Invite = { ...INVITE, id: 6, invitee_email: "member@example.com" };

async function panel() {
  const wrapper = mount(InvitesPanel);
  await flushPromises();
  return wrapper;
}

type Panel = Awaited<ReturnType<typeof panel>>;

const confirmDialog = (wrapper: Panel) => wrapper.getComponent(ConfirmModal);
const emailField = (wrapper: Panel) => wrapper.get<HTMLInputElement>('input[type="email"]');
const submit = (wrapper: Panel) => wrapper.get('button[type="submit"]');

async function openDrawer(wrapper: Panel) {
  wrapper.vm.openCreate();
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  client.listInvites.mockResolvedValue([INVITE]);
  client.inviteEmailStatus.mockResolvedValue({ ready: true, reason: null });
});

describe("InvitesPanel", () => {
  it("lists the open invites", async () => {
    const wrapper = await panel();

    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.get("tbody").text()).toContain("new@mail.com");
    expect(wrapper.findAll("th").map((header) => header.text())).toEqual(["Invitee", "Created", "Expires", ""]);
  });

  it("says when there are none", async () => {
    client.listInvites.mockResolvedValue([]);

    expect((await panel()).text()).toContain("No open invites.");
  });

  it("shows an error when the list cannot be read", async () => {
    client.listInvites.mockRejectedValue(new ApiError(500, "boom"));

    expect((await panel()).text()).toContain("boom");
  });

  it("checks email once when Invite member opens and requires a valid address", async () => {
    const wrapper = await panel();
    expect(client.inviteEmailStatus).not.toHaveBeenCalled();
    await openDrawer(wrapper);

    expect(wrapper.get('dialog[aria-label="Invite member"] h3').text()).toBe("Invite member");
    expect(client.inviteEmailStatus).toHaveBeenCalledTimes(1);
    expect(emailField(wrapper).attributes("required")).toBeDefined();
    expect(submit(wrapper).attributes("disabled")).toBeDefined();
    await emailField(wrapper).setValue("invalid");
    expect(submit(wrapper).attributes("disabled")).toBeDefined();
    await emailField(wrapper).setValue("member@example.com");
    expect(submit(wrapper).attributes("disabled")).toBeUndefined();
    expect(submit(wrapper).text()).toBe("Send invite");
  });

  it("shows why email is blocked and enables sending after checking again", async () => {
    const reason = "The Email capability is switched off in Armory.";
    client.inviteEmailStatus.mockResolvedValueOnce({ ready: false, reason });
    const wrapper = await panel();
    await openDrawer(wrapper);
    await emailField(wrapper).setValue("member@example.com");

    expect(wrapper.get(".invite-create .error").text()).toBe(reason);
    expect(submit(wrapper).attributes("disabled")).toBeDefined();
    await wrapper.get("form").trigger("submit");
    expect(client.createInvite).not.toHaveBeenCalled();

    const checkAgain = wrapper.findAll("button").find((button) => button.text() === "Check again")!;
    await checkAgain.trigger("click");
    await flushPromises();
    expect(client.inviteEmailStatus).toHaveBeenCalledTimes(2);
    expect(submit(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("shows a confirmation, reloads the list and emits changed after sending", async () => {
    client.createInvite.mockResolvedValue(CREATED);
    client.listInvites.mockResolvedValueOnce([INVITE]).mockResolvedValue([INVITE, CREATED]);
    const wrapper = await panel();
    await openDrawer(wrapper);
    await emailField(wrapper).setValue("member@example.com");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(client.createInvite).toHaveBeenCalledWith("member@example.com");
    const drawer = wrapper.get('dialog[aria-label="Invite member"]');
    expect(drawer.get('[role="status"]').text()).toBe("Invitation sent to member@example.com.");
    expect(drawer.find("code").exists()).toBe(false);
    expect(drawer.text()).not.toMatch(/copy|only once/i);
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
    expect(client.listInvites).toHaveBeenCalledTimes(2);
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("shows the 503 reason and keeps the address available to retry", async () => {
    client.createInvite.mockRejectedValue(new ApiError(503, "Email could not be sent."));
    const wrapper = await panel();
    await openDrawer(wrapper);
    await emailField(wrapper).setValue("member@example.com");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get(".invite-create .error").text()).toBe("Email could not be sent.");
    expect(emailField(wrapper).element.value).toBe("member@example.com");
    expect(submit(wrapper).attributes("disabled")).toBeUndefined();
    expect(wrapper.emitted("changed")).toBeUndefined();
  });

  it("asks before revoking, and does nothing when cancelled", async () => {
    const wrapper = await panel();

    await wrapper.get("tbody button.danger").trigger("click");
    expect(confirmDialog(wrapper).props("open")).toBe(true);
    expect(confirmDialog(wrapper).props("message")).toBe("Revoke new@mail.com? Its code stops working.");

    await confirmDialog(wrapper).get(".cancel").trigger("click");

    expect(confirmDialog(wrapper).props("open")).toBe(false);
    expect(client.revokeInvite).not.toHaveBeenCalled();
  });

  it("revokes once confirmed and removes the row", async () => {
    client.revokeInvite.mockResolvedValue(undefined);
    const wrapper = await panel();

    await wrapper.get("tbody button.danger").trigger("click");
    await confirmDialog(wrapper).get(".confirm").trigger("click");
    await flushPromises();

    expect(client.revokeInvite).toHaveBeenCalledWith(5);
    expect(wrapper.find("tbody").exists()).toBe(false);
    expect(confirmDialog(wrapper).props("open")).toBe(false);
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("shows why a revoke failed and keeps the row", async () => {
    client.revokeInvite.mockRejectedValue(new ApiError(409, "That invite was already used"));
    const wrapper = await panel();

    await wrapper.get("tbody button.danger").trigger("click");
    await confirmDialog(wrapper).get(".confirm").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("already used");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.emitted("changed")).toBeUndefined();
  });
});
