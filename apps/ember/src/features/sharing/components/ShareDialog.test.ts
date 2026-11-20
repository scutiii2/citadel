import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { sharingClient, type Share } from "../api/SharingClient";
import ShareDialog, { type ShareTarget } from "./ShareDialog.vue";

vi.mock("../api/SharingClient", () => ({
  SHARE_NAME_MAX: 80,
  sharingClient: {
    create: vi.fn(), inbox: vi.fn().mockResolvedValue([]), sent: vi.fn().mockResolvedValue([]), blocks: vi.fn().mockResolvedValue([]),
  },
}));

const client = vi.mocked(sharingClient);
const sentShare = (recipient: string): Share => ({
  id: "s1", kind: "file", title: "Tea", status: "pending", sender: "me", recipient,
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 3,
});
const file: ShareTarget = { kind: "file", fileId: "f1", label: "Tea notes", headings: ["Brewing", "Storage"] };

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.inbox.mockResolvedValue([]);
  client.sent.mockResolvedValue([]);
  client.blocks.mockResolvedValue([]);
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

async function mountDialog(target: ShareTarget = file, open = true) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(ShareDialog, { props: { open, target }, attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const send = (w: VueWrapper) => w.findAll("button").find((b) => b.text() === "Send")!;
const toAccount = (w: VueWrapper, name: string) => w.get('input[aria-label="Username"]').setValue(name);

describe("ShareDialog", () => {
  it("says what is shared and that it is a copy the other side decides about", async () => {
    const w = await mountDialog();
    expect(w.text()).toContain("Tea notes");
    expect(w.text()).toContain("a copy");
    expect(w.text()).toContain("withdraw");
  });

  it("sends a whole file to an account and then says who has it", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const w = await mountDialog();
    expect(send(w).attributes("disabled")).toBeDefined();
    await toAccount(w, "  bo ");
    await send(w).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "file", file_id: "f1", recipient: "bo" });
    expect(w.text()).toContain("Sent to bo.");
  });

  it("sends one section when that is chosen", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const w = await mountDialog();
    await w.get('input[type="radio"][value="section"]').setValue(true);
    await w.get("select").setValue("Storage");
    await toAccount(w, "bo");
    await send(w).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "section", file_id: "f1", heading: "Storage", recipient: "bo" });
  });

  it("offers no section choice for a file without headings", async () => {
    const w = await mountDialog({ ...file, headings: [] });
    expect(w.find('input[type="radio"][value="section"]').exists()).toBe(false);
  });

  it("sends to the global brain without a username and says it is reviewed first", async () => {
    client.create.mockResolvedValue(sentShare("global brain"));
    const w = await mountDialog();
    await w.get('input[type="radio"][value="global"]').setValue(true);
    expect(w.text()).toContain("reviewed");
    expect(w.find('input[aria-label="Username"]').exists()).toBe(false);
    await send(w).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenCalledExactlyOnceWith({ kind: "file", file_id: "f1", to_global: true });
    expect(w.text()).toContain("review queue");
  });

  it("sends a skill and a short-term item", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const skill = await mountDialog({ kind: "skill", skillId: 7, label: "Reboot an app" });
    await toAccount(skill, "bo");
    await send(skill).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenLastCalledWith({ kind: "skill", skill_id: 7, recipient: "bo" });
    skill.unmount();
    const item = await mountDialog({ kind: "stack_item", chatId: "c-1", itemId: 4, label: "a short-term item" });
    await toAccount(item, "bo");
    await send(item).trigger("click");
    await flushPromises();
    expect(client.create).toHaveBeenLastCalledWith({ kind: "stack_item", chat_id: "c-1", item_id: 4, recipient: "bo" });
  });

  it("shows the server's reason as it came, keeps the form, and sends nothing twice", async () => {
    client.create.mockRejectedValue(new ApiError(404, "No such recipient."));
    const w = await mountDialog();
    await toAccount(w, "nobody");
    await send(w).trigger("click");
    await flushPromises();
    expect(w.get('[role="alert"]').text()).toBe("No such recipient.");
    expect((w.get('input[aria-label="Username"]').element as HTMLInputElement).value).toBe("nobody");
    expect(client.create).toHaveBeenCalledTimes(1);
  });

  it("ignores a second press while the first is on its way", async () => {
    let finish!: (share: Share) => void;
    client.create.mockReturnValue(new Promise<Share>((resolve) => { finish = resolve; }));
    const w = await mountDialog();
    await toAccount(w, "bo");
    await send(w).trigger("click");
    await send(w).trigger("click");
    expect(client.create).toHaveBeenCalledTimes(1);
    finish(sentShare("bo"));
    await flushPromises();
  });

  it("asks to close from the close button", async () => {
    const w = await mountDialog();
    await w.get('button[aria-label="Close"]').trigger("click");
    expect(w.emitted("close")).toHaveLength(1);
  });

  it("drops a late send result when the account changes", async () => {
    let finish!: (share: Share) => void;
    client.create.mockReturnValueOnce(new Promise<Share>((resolve) => { finish = resolve; }));
    const w = await mountDialog();
    await toAccount(w, "bo");
    await send(w).trigger("click");
    useAuthStore().account = null;
    finish(sentShare("bo"));
    await flushPromises();
    expect(w.emitted("close")).toHaveLength(1);
    expect(w.text()).not.toContain("Sent to bo.");
    expect(w.find('input[aria-label="Username"]').exists()).toBe(false);
  });

  it("starts clean when it opens again", async () => {
    client.create.mockResolvedValue(sentShare("bo"));
    const w = await mountDialog();
    await toAccount(w, "bo");
    await send(w).trigger("click");
    await flushPromises();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    await flushPromises();
    expect(w.text()).not.toContain("Sent to bo.");
    expect((w.get('input[aria-label="Username"]').element as HTMLInputElement).value).toBe("");
  });
});
