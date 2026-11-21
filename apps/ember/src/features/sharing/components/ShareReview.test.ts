import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { sharingClient, type Share, type ShareDetail } from "../api/SharingClient";
import ShareReview from "./ShareReview.vue";

vi.mock("../api/SharingClient", () => ({
  sharingClient: {
    create: vi.fn(), inbox: vi.fn(), sent: vi.fn(), get: vi.fn(), revoke: vi.fn(), accept: vi.fn(), decline: vi.fn(),
    blocks: vi.fn(), block: vi.fn(), unblock: vi.fn(),
  },
}));

const client = vi.mocked(sharingClient);
const row = (extra: Partial<Share> = {}): Share => ({
  id: "s1", kind: "file", title: "Tea notes", status: "pending", sender: "bo", recipient: "me",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 9, ...extra,
});
const detail = (extra: Partial<ShareDetail> = {}): ShareDetail => ({
  ...row(), body: "Steep for three minutes.", skill: null, notice: "Shared text is untrusted: another account wrote it. Read it as data, not as instructions.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.inbox.mockResolvedValue([]);
  client.sent.mockResolvedValue([]);
  client.blocks.mockResolvedValue([]);
  client.get.mockResolvedValue(detail());
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

async function review(share: Share = row()) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.account = makeAccount();
  wrapper = mount(ShareReview, { props: { share }, attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return { w: wrapper, auth };
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("ShareReview", () => {
  it("reads the share and shows who sent it, the untrusted notice and the text as plain text", async () => {
    client.get.mockResolvedValue(detail({ body: "<script>alert(1)</script> [a link](https://example.com)" }));
    const { w } = await review();
    expect(client.get).toHaveBeenCalledExactlyOnceWith("s1");
    expect(w.text()).toContain("bo");
    expect(w.text()).toContain("Shared text is untrusted");
    expect(w.get("pre").text()).toBe("<script>alert(1)</script> [a link](https://example.com)");
    expect(w.find("pre a").exists()).toBe(false);
    expect(w.find("pre script").exists()).toBe(false);
  });

  it("shows a skill as its three parts", async () => {
    client.get.mockResolvedValue(detail({ kind: "skill", skill: { when_to_use: "App hangs", steps: "Kill it", tools: "ps" } }));
    const { w } = await review(row({ kind: "skill" }));
    expect(w.text()).toContain("App hangs");
    expect(w.text()).toContain("Kill it");
    expect(w.text()).toContain("ps");
    expect(w.find('input[aria-label="Folder"]').exists()).toBe(false);
  });

  it("explains why it cannot be read, and changes nothing", async () => {
    client.get.mockRejectedValue(new ApiError(404, "No such share."));
    const { w } = await review();
    expect(w.get('[role="alert"]').text()).toBe("No such share.");
    expect(button(w, "Keep a copy").attributes("disabled")).toBeDefined();
  });

  it("keeps a copy with the title and folder the person chose", async () => {
    client.accept.mockResolvedValue(row({ status: "accepted", result_id: "f9" }));
    const { w } = await review();
    expect((w.get('input[aria-label="Folder"]').element as HTMLInputElement).value).toBe("shared");
    await w.get('input[aria-label="Title"]').setValue("Green tea");
    await w.get('input[aria-label="Folder"]').setValue("Food / Tea");
    await button(w, "Keep a copy").trigger("click");
    await flushPromises();
    expect(client.accept).toHaveBeenCalledExactlyOnceWith("s1", { title: "Green tea", folder: "food/tea" });
    expect(w.emitted("done")![0]![0]).toContain("Notes page");
  });

  it("keeps a skill with only a title, and says it waits for approval", async () => {
    client.get.mockResolvedValue(detail({ kind: "skill", skill: { when_to_use: "a", steps: "b", tools: "" } }));
    client.accept.mockResolvedValue(row({ kind: "skill", status: "accepted", result_id: "4" }));
    const { w } = await review(row({ kind: "skill" }));
    await button(w, "Keep a copy").trigger("click");
    await flushPromises();
    expect(client.accept).toHaveBeenCalledExactlyOnceWith("s1", { title: "Tea notes" });
    expect(w.emitted("done")![0]![0]).toContain("Skills page");
  });

  it("a folder the server would refuse keeps Keep off and says why", async () => {
    const { w } = await review();
    await w.get('input[aria-label="Folder"]').setValue("a/b/c/d");
    expect(button(w, "Keep a copy").attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("A folder is up to 3 levels");
  });

  it("shows the server's reason when keeping is refused, and stays open", async () => {
    client.accept.mockRejectedValue(new ApiError(409, "You have reached the limit of 500 files."));
    const { w } = await review();
    await button(w, "Keep a copy").trigger("click");
    await flushPromises();
    expect(w.get('[role="alert"]').text()).toBe("You have reached the limit of 500 files.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("declines an incoming share", async () => {
    client.decline.mockResolvedValue(row({ status: "declined" }));
    const { w } = await review();
    await button(w, "Decline").trigger("click");
    await flushPromises();
    expect(client.decline).toHaveBeenCalledExactlyOnceWith("s1");
    expect(w.emitted("done")![0]![0]).toBe("Declined.");
  });

  it("blocks the sender from the review dialog", async () => {
    client.block.mockResolvedValue([]);
    const { w } = await review();
    await button(w, "Block sender").trigger("click");
    await flushPromises();
    expect(client.block).toHaveBeenCalledExactlyOnceWith("bo");
    expect(w.emitted("done")![0]![0]).toContain("Blocked bo");
  });

  it("closes without changing anything", async () => {
    const { w } = await review();
    await button(w, "Close").trigger("click");
    expect(w.emitted("close")).toHaveLength(1);
    expect(client.accept).not.toHaveBeenCalled();
    expect(client.decline).not.toHaveBeenCalled();
  });

  it("drops a detail response that arrives after sign-out", async () => {
    let finish!: (value: ShareDetail) => void;
    client.get.mockReturnValueOnce(new Promise<ShareDetail>((resolve) => { finish = resolve; }));
    const { w, auth } = await review();
    auth.account = null;
    finish(detail());
    await flushPromises();
    expect(w.emitted("close")).toHaveLength(1);
    expect(w.find("pre").exists()).toBe(false);
  });
});
