import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forgeClient, type ForgeGroup, type ForgeWorker } from "../api/ForgeClient";
import { watchGroup } from "../services/forgeStream";
import { useAuthStore } from "../stores/auth";
import ForgeView from "./ForgeView.vue";

vi.mock("../api/ForgeClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/ForgeClient")>()),
  forgeClient: {
    plans: vi.fn(), setPlans: vi.fn(), workers: vi.fn(), createWorker: vi.fn(), removeWorker: vi.fn(),
    groups: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), removeGroup: vi.fn(),
    invite: vi.fn(), removeMember: vi.fn(), send: vi.fn(), answerPermission: vi.fn(), stop: vi.fn(),
  },
}));
vi.mock("../services/forgeStream", () => ({ watchGroup: vi.fn() }));

const client = vi.mocked(forgeClient);
const watch = vi.mocked(watchGroup);

const ACCOUNT = { id: 1, username: "u", email: "u@example.com", email_verified: true, roles: [], permissions: ["forge.use"] };
const worker = (id: number, label: string, extra: Partial<ForgeWorker> = {}): ForgeWorker => ({
  id, provider: "claude", label, reported_plan: "Max", online: true, eligible: true, problem: null, last_seen: null, created_at: "2026-10-18T10:00:00", ...extra,
});
const member = { worker_id: 1, label: "claude", provider: "claude" as const, folder: "C:/site", online: true };
const group = (id: number, extra: Partial<ForgeGroup> = {}): ForgeGroup => ({
  id, title: `Group ${id}`, mode: "ask", relay: false, running: false, created_at: "2026-10-18T10:00:00", members: [member], ...extra,
});

let wrapper: VueWrapper;
const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.resetAllMocks();
  setActivePinia(createPinia());
  useAuthStore().account = ACCOUNT;
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  client.workers.mockResolvedValue([worker(1, "claude")]);
  client.groups.mockResolvedValue([group(1)]);
  client.plans.mockResolvedValue({ claude: ["max"], codex: [] });
  watch.mockImplementation(() => new Promise(() => {}));
});
afterEach(() => {
  wrapper?.unmount();
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});

async function setup() {
  wrapper = mount(ForgeView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const button = (text: string) => wrapper.findAll("button").find((b) => b.text() === text)!;
const groupButton = (title: string) => wrapper.findAll("button.group").find((b) => b.get(".title").text() === title)!;
const events = () => watch.mock.calls.at(-1)![2];

describe("ForgeView", () => {
  it("guides the user to add a worker first", async () => {
    client.workers.mockResolvedValue([]);
    client.groups.mockResolvedValue([]);
    await setup();

    expect(wrapper.text()).toContain("Add a worker");
    expect(wrapper.text()).toContain("your own Claude Code or Codex");
  });

  it("invites the user to make a first group once there is a worker", async () => {
    client.groups.mockResolvedValue([]);
    await setup();

    expect(wrapper.text()).toContain("Create your first group");
  });

  it("opens a group and shows what happens in it", async () => {
    await setup();

    await groupButton("Group 1").trigger("click");
    events()({ type: "message", seq: 1, sender: "user", kind: "text", body: { text: "@claude look" }, created_at: "2026-10-18T10:00:00" });
    events()({ type: "delta", turn_id: "t", sender: "1", label: "claude", text: "Looking" });
    await flushPromises();

    expect(watch.mock.calls.at(-1)![0]).toBe(1);
    expect(wrapper.text()).toContain("@claude look");
    expect(wrapper.text()).toContain("Looking");
  });

  it("sends a message and clears the box; a refusal keeps the text and shows why", async () => {
    await setup();
    await groupButton("Group 1").trigger("click");
    client.send.mockRejectedValueOnce(new Error("A worker is still answering. Wait for it or stop it."));

    await wrapper.get("textarea").setValue("@claude hi");
    await wrapper.get("form.composer").trigger("submit");
    await flushPromises();
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("@claude hi");
    expect(wrapper.get("[role=alert]").text()).toContain("still answering");

    client.send.mockResolvedValue({} as never);
    await wrapper.get("form.composer").trigger("submit");
    await flushPromises();
    expect(client.send).toHaveBeenLastCalledWith(1, "@claude hi");
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("");
  });

  it("answers a permission request", async () => {
    await setup();
    await groupButton("Group 1").trigger("click");
    events()({ type: "message", seq: 1, sender: "1", kind: "permission_request", body: { request_id: "r1", turn_id: "t", label: "claude", tool: "Bash", summary: "npm test" }, created_at: "2026-10-18T10:00:00" });
    await flushPromises();
    client.answerPermission.mockResolvedValue({ answered: true });

    await wrapper.get("button.allow").trigger("click");

    expect(client.answerPermission).toHaveBeenCalledWith(1, "r1", true);
  });

  it("shows Stop while a turn runs and stops it", async () => {
    await setup();
    await groupButton("Group 1").trigger("click");
    events()({ type: "turn", running: true });
    await flushPromises();
    client.stop.mockResolvedValue({ stopping: true });

    await wrapper.get("button.stop").trigger("click");

    expect(client.stop).toHaveBeenCalledWith(1);
  });

  it("changes mode and relay at once", async () => {
    await setup();
    await groupButton("Group 1").trigger("click");
    client.updateGroup.mockResolvedValue(group(1, { mode: "plan" }));

    await button("Plan").trigger("click");
    await flushPromises();
    expect(client.updateGroup).toHaveBeenCalledWith(1, { mode: "plan" });

    client.updateGroup.mockResolvedValue(group(1, { relay: true }));
    await wrapper.get("input[role=switch]").setValue(true);
    await flushPromises();
    expect(client.updateGroup).toHaveBeenLastCalledWith(1, { relay: true });
  });

  it("makes the user type the phrase before switching to full auto", async () => {
    await setup();
    await groupButton("Group 1").trigger("click");

    await button("Full auto").trigger("click");
    const confirm = wrapper.findAll("dialog").find((d) => d.attributes("aria-label")?.includes("full auto"))!;
    const ok = () => confirm.get(".confirm");
    expect(client.updateGroup).not.toHaveBeenCalled();
    expect((ok().element as HTMLButtonElement).disabled).toBe(true);

    client.updateGroup.mockResolvedValue(group(1, { mode: "full_auto" }));
    await confirm.get("input[type=text]").setValue("full auto");
    await ok().trigger("click");
    await flushPromises();

    expect(client.updateGroup).toHaveBeenCalledWith(1, { mode: "full_auto", confirm_full_auto: true });
  });

  it("creates a group from the dialog", async () => {
    await setup();
    client.createGroup.mockResolvedValue(group(2, { title: "Docs" }));

    await button("New group").trigger("click");
    const dialog = wrapper.findAll("dialog").find((d) => d.attributes("aria-label") === "New group")!;
    await dialog.get("input[type=text]").setValue("Docs");
    await dialog.get("form").trigger("submit");
    await flushPromises();

    expect(client.createGroup).toHaveBeenCalledWith("Docs", "ask");
  });

  it("invites a worker and shows the server's refusal", async () => {
    client.groups.mockResolvedValue([group(1, { members: [] })]);
    await setup();
    await groupButton("Group 1").trigger("click");
    client.invite.mockRejectedValueOnce(new Error("Plan not eligible: Pro"));

    await button("Invite a worker").trigger("click");
    const dialog = wrapper.findAll("dialog").find((d) => d.attributes("aria-label") === "Invite a worker")!;
    await dialog.get("input[type=radio]").setValue(true);
    await dialog.get("input[type=text]").setValue("C:/site");
    await dialog.get("form").trigger("submit");
    await flushPromises();

    expect(client.invite).toHaveBeenCalledWith(1, 1, "C:/site");
    expect(dialog.get("[role=alert]").text()).toContain("Plan not eligible: Pro");
  });

  it("deletes a group only after confirmation", async () => {
    await setup();
    await groupButton("Group 1").trigger("click");

    await button("Delete group").trigger("click");
    expect(client.removeGroup).not.toHaveBeenCalled();
    const confirm = wrapper.findAll("dialog").find((d) => d.attributes("aria-label") === "Delete this group?")!;
    client.removeGroup.mockResolvedValue(undefined);
    await confirm.get("input[type=text]").setValue("Group 1");
    await confirm.get(".confirm").trigger("click");
    await flushPromises();

    expect(client.removeGroup).toHaveBeenCalledWith(1);
  });

  it("makes a worker and shows its token once", async () => {
    await setup();
    client.createWorker.mockResolvedValue({ ...worker(9, "codex", { provider: "codex" }), token: "ft_once" });

    await button("Workers").trigger("click");
    const dialog = wrapper.findAll("dialog").find((d) => d.attributes("aria-label") === "Workers")!;
    await dialog.findAll("button").find((b) => b.text() === "Codex")!.trigger("click");
    await dialog.get("form.add").trigger("submit");
    await flushPromises();

    expect(client.createWorker).toHaveBeenCalledWith("codex", "codex");
    expect(dialog.text()).toContain("ft_once");

    await dialog.findAll("button").find((b) => b.text() === "Done")!.trigger("click");
    expect(wrapper.text()).not.toContain("ft_once");
  });

  it("offers the plan editor only to people who can change settings", async () => {
    await setup();
    await button("Workers").trigger("click");
    expect(wrapper.text()).not.toContain("Eligible plans");

    useAuthStore().account = { ...ACCOUNT, permissions: ["forge.use", "settings.manage"] };
    await flushPromises();
    await setup();
    await button("Workers").trigger("click");
    expect(wrapper.text()).toContain("Eligible plans");
  });

  it("warns when the live connection is lost and reconnects on request", async () => {
    await setup();
    watch.mockRejectedValueOnce(new Error("Lost the connection to ember_api"));
    await groupButton("Group 1").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Connection lost");
    await button("Reconnect").trigger("click");

    expect(watch).toHaveBeenCalledTimes(2);
  });

  it("explains an empty group in the composer", async () => {
    client.groups.mockResolvedValue([group(1, { members: [] })]);
    await setup();
    await groupButton("Group 1").trigger("click");

    expect(wrapper.text()).toContain("Invite a worker first.");
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).disabled).toBe(true);
  });
});
