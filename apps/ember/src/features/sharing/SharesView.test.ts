import { flushPromises, mount, RouterLinkStub, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import { sharingClient, type Block, type Share } from "./api/SharingClient";
import SharesView from "./SharesView.vue";
import { useSharingStore } from "./stores/sharing";

vi.mock("./api/SharingClient", () => ({
  SHARE_NAME_MAX: 80,
  sharingClient: {
    create: vi.fn(), inbox: vi.fn(), sent: vi.fn(), get: vi.fn(), revoke: vi.fn(), accept: vi.fn(), decline: vi.fn(),
    blocks: vi.fn(), block: vi.fn(), unblock: vi.fn(),
  },
}));
vi.mock("./components/ShareReview.vue", () => ({
  default: {
    props: ["share"],
    emits: ["close", "done"],
    template: '<div data-test="review"><button class="done" @click="$emit(\'done\', \'Kept as a file.\', \'notes\')">done</button><button class="close" @click="$emit(\'close\')">close</button>{{ share.title }}</div>',
  },
}));

const client = vi.mocked(sharingClient);
const share = (id: string, extra: Partial<Share> = {}): Share => ({
  id, kind: "file", title: `share ${id}`, status: "pending", sender: "bo", recipient: "me",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 5, ...extra,
});
const blocked = (uid: string): Block => ({ uid, username: `user-${uid}`, created_at: "2026-01-01T00:00:00Z" });

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

async function setup(lists: { inbox?: Share[]; sent?: Share[]; blocks?: Block[] } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  client.inbox.mockResolvedValue(lists.inbox ?? []);
  client.sent.mockResolvedValue(lists.sent ?? []);
  client.blocks.mockResolvedValue(lists.blocks ?? []);
  wrapper = mount(SharesView, { attachTo: document.body, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } });
  await flushPromises();
  return wrapper;
}
const section = (w: VueWrapper, name: string) => w.get(`section[aria-label="${name}"]`);
const buttonIn = (el: ReturnType<typeof section>, text: string) => el.findAll("button").find((b) => b.text() === text)!;
const confirm = () => document.body.querySelector<HTMLButtonElement>("dialog[open] .confirm");

beforeEach(() => {
  vi.clearAllMocks();
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

describe("SharesView", () => {
  it("lists what is waiting, what was sent and who is blocked", async () => {
    const w = await setup({
      inbox: [share("a", { kind: "skill", sender: "bo" })],
      sent: [share("s1", { sender: "me", recipient: "cy", status: "accepted" }), share("s2", { sender: "me", recipient: "global brain" })],
      blocks: [blocked("u1")],
    });
    expect(section(w, "Waiting for you").text()).toContain("share a");
    expect(section(w, "Waiting for you").text()).toContain("bo");
    expect(section(w, "Waiting for you").text()).toContain("Skill");
    expect(section(w, "Sent by you").text()).toContain("cy");
    expect(section(w, "Sent by you").text()).toContain("Kept");
    expect(section(w, "Sent by you").text()).toContain("global brain");
    expect(section(w, "Blocked accounts").text()).toContain("user-u1");
  });

  it("says each list is empty", async () => {
    const w = await setup();
    expect(section(w, "Waiting for you").text()).toContain("Nothing is waiting for you.");
    expect(section(w, "Sent by you").text()).toContain("You have not shared anything.");
    expect(section(w, "Blocked accounts").text()).toContain("You have not blocked anyone.");
  });

  it("opens the review dialog for a share and shows what it reports", async () => {
    const w = await setup({ inbox: [share("a")] });
    await buttonIn(section(w, "Waiting for you"), "Review").trigger("click");
    expect(w.get('[data-test="review"]').text()).toContain("share a");
    await w.get(".done").trigger("click");
    expect(w.find('[data-test="review"]').exists()).toBe(false);
    expect(w.get('[role="status"]').text()).toContain("Kept as a file.");
    expect(w.getComponent(RouterLinkStub).props("to")).toEqual({ name: "notes" });
  });

  it("leaving the review closes it without a message", async () => {
    const w = await setup({ inbox: [share("a")] });
    await buttonIn(section(w, "Waiting for you"), "Review").trigger("click");
    await w.get(".close").trigger("click");
    expect(w.find('[data-test="review"]').exists()).toBe(false);
    expect(w.find('[role="status"]').exists()).toBe(false);
  });

  it("withdraws a waiting share after asking, and only a waiting one has the button", async () => {
    const w = await setup({ sent: [share("s1", { sender: "me", recipient: "cy" }), share("s2", { sender: "me", recipient: "cy", status: "declined" })] });
    const sent = section(w, "Sent by you");
    expect(sent.findAll("button").filter((b) => b.text() === "Withdraw")).toHaveLength(1);
    await buttonIn(sent, "Withdraw").trigger("click");
    await flushPromises();
    expect(client.revoke).not.toHaveBeenCalled();
    client.revoke.mockResolvedValue(share("s1", { status: "revoked" }));
    confirm()!.click();
    await flushPromises();
    expect(client.revoke).toHaveBeenCalledExactlyOnceWith("s1");
    expect(w.text()).toContain("Share withdrawn.");
  });

  it("shows why a withdrawal was refused", async () => {
    const w = await setup({ sent: [share("s1", { sender: "me", recipient: "cy" })] });
    await buttonIn(section(w, "Sent by you"), "Withdraw").trigger("click");
    await flushPromises();
    client.revoke.mockRejectedValue(new ApiError(409, "That share is already decided."));
    confirm()!.click();
    await flushPromises();
    expect(w.get('[role="alert"]').text()).toBe("That share is already decided.");
  });

  it("blocks an account by username and shows the server's one refusal as it came", async () => {
    const w = await setup();
    client.block.mockRejectedValueOnce(new ApiError(404, "No such recipient."));
    await w.get('input[aria-label="Username to block"]').setValue(" nobody ");
    await buttonIn(section(w, "Blocked accounts"), "Block").trigger("click");
    await flushPromises();
    expect(client.block).toHaveBeenCalledWith("nobody");
    expect(section(w, "Blocked accounts").get('[role="alert"]').text()).toBe("No such recipient.");
    client.block.mockResolvedValueOnce([blocked("u1")]);
    client.blocks.mockResolvedValue([blocked("u1")]);
    await buttonIn(section(w, "Blocked accounts"), "Block").trigger("click");
    await flushPromises();
    expect(section(w, "Blocked accounts").text()).toContain("user-u1");
    expect((w.get('input[aria-label="Username to block"]').element as HTMLInputElement).value).toBe("");
  });

  it("unblocks an account", async () => {
    const w = await setup({ blocks: [blocked("u1")] });
    client.unblock.mockResolvedValue(undefined);
    client.blocks.mockResolvedValue([]);
    await buttonIn(section(w, "Blocked accounts"), "Unblock").trigger("click");
    await flushPromises();
    expect(client.unblock).toHaveBeenCalledExactlyOnceWith("u1");
    expect(section(w, "Blocked accounts").text()).toContain("You have not blocked anyone.");
  });

  it("a failed load shows the reason with a way to try again", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().account = makeAccount();
    client.inbox.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    client.sent.mockResolvedValue([]);
    client.blocks.mockResolvedValue([]);
    wrapper = mount(SharesView, { attachTo: document.body, global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } } });
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("Storage is unavailable");
    client.inbox.mockResolvedValue([share("a")]);
    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();
    expect(section(wrapper, "Waiting for you").text()).toContain("share a");
  });

  it("drops private page state and ignores a late withdrawal after sign-out", async () => {
    const w = await setup({ sent: [share("s1")], blocks: [blocked("u1")] });
    await w.get('input[aria-label="Username to block"]').setValue("pending-name");
    await buttonIn(section(w, "Sent by you"), "Withdraw").trigger("click");
    await flushPromises();
    let finish!: (value: Share) => void;
    client.revoke.mockReturnValueOnce(new Promise<Share>((resolve) => { finish = resolve; }));
    confirm()!.click();
    useAuthStore().account = null;
    finish(share("s1", { status: "revoked" }));
    await flushPromises();
    expect(w.text()).not.toContain("Share withdrawn.");
    expect(w.text()).not.toContain("user-u1");
    expect(document.querySelector("dialog[open]")).toBeNull();
    expect(w.find('input[aria-label="Username to block"]').exists()).toBe(false);
  });

  it("drops the lists when the page goes away", async () => {
    const w = await setup({ inbox: [share("a")] });
    const store = useSharingStore();
    expect(store.inbox).toHaveLength(1);
    w.unmount();
    wrapper = null;
    expect(store.inbox).toEqual([]);
  });
});
