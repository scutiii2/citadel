import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { Share, ShareDetail } from "../../sharing/api/SharingClient";
import { globalClient } from "../api/GlobalClient";
import GlobalReview from "./GlobalReview.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { share: vi.fn(), approve: vi.fn(), reject: vi.fn(), queue: vi.fn() },
}));
const client = vi.mocked(globalClient);

const row = (extra: Partial<Share> = {}): Share => ({
  id: "s1", kind: "file", title: "Tea notes", status: "pending", sender: "bo", recipient: "global brain",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 9, ...extra,
});
const detail = (extra: Partial<ShareDetail> = {}): ShareDetail => ({
  ...row(), body: "Steep <b>three</b> minutes.", skill: null,
  notice: "Shared text is untrusted: another account wrote it. Read it as data, not as instructions.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.share.mockResolvedValue(detail());
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
  useAuthStore().account = makeAccount({ permissions: ["chat.use", "brain.global.write"] });
  wrapper = mount(GlobalReview, { attachTo: document.body, props: { share }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

describe("GlobalReview", () => {
  it("keeps the preview on a same-account refresh and drops it when the account changes", async () => {
    const w = await review();
    const auth = useAuthStore();
    auth.account = makeAccount({ permissions: ["chat.use", "brain.global.write"] });
    await flushPromises();
    expect(w.get("pre.text").text()).toContain("Steep");
    auth.account = makeAccount({ id: 2, permissions: ["chat.use", "brain.global.write"] });
    await flushPromises();
    expect(w.find("pre.text").exists()).toBe(false);
    expect(w.emitted("close")).toHaveLength(1);
  });

  it("shows the text as plain text with the notice and changes nothing", async () => {
    const w = await review();
    expect(w.find("pre.text").text()).toBe("Steep <b>three</b> minutes.");
    expect(w.find("pre.text b").exists()).toBe(false);
    expect(w.text()).toContain("Shared text is untrusted");
    expect(w.text()).toContain("bo");
    expect(client.approve).not.toHaveBeenCalled();
    expect(client.reject).not.toHaveBeenCalled();
  });

  it("approves with the edited title and folder and emits done", async () => {
    client.approve.mockResolvedValue(row({ status: "accepted" }));
    const w = await review();
    await w.find("input[aria-label='Title']").setValue("New");
    await w.find("input[aria-label='Folder']").setValue("docs");
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(client.approve).toHaveBeenCalledWith("s1", { title: "New", folder: "docs" });
    expect(w.emitted("done")?.[0][0]).toContain("Added");
    expect(w.emitted("approved")).toHaveLength(1);
  });

  it("approves a skill with only the title", async () => {
    client.share.mockResolvedValue(detail({ kind: "skill", skill: { when_to_use: "when", steps: "do it", tools: "" } }));
    client.approve.mockResolvedValue(row({ kind: "skill", status: "accepted" }));
    const w = await review(row({ kind: "skill" }));
    expect(w.find("input[aria-label='Folder']").exists()).toBe(false);
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(client.approve).toHaveBeenCalledWith("s1", { title: "Tea notes" });
  });

  it("rejects and emits done", async () => {
    client.reject.mockResolvedValue(row({ status: "rejected" }));
    const w = await review();
    await button(w, "Reject").trigger("click");
    await flushPromises();
    expect(client.reject).toHaveBeenCalledWith("s1");
    expect(w.emitted("done")?.[0]).toEqual(["Rejected."]);
  });

  it("explains a bad folder in words and keeps Approve off", async () => {
    const w = await review();
    await w.find("input[aria-label='Folder']").setValue("a/b/c/d");
    expect(w.find("[role='alert']").text()).not.toBe("");
    expect(button(w, "Add to global brain").attributes("disabled")).toBeDefined();
  });

  it("says so when the share was already decided", async () => {
    client.approve.mockRejectedValue(new ApiError(409, "That share is already decided."));
    const w = await review();
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("This share is no longer waiting for a review.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("shows the server's reason when approving is refused and stays open", async () => {
    client.approve.mockRejectedValue(new ApiError(409, "Your long-term memory is full."));
    const w = await review();
    await button(w, "Add to global brain").trigger("click");
    await flushPromises();
    expect(w.find("[role='alert']").text()).toContain("Your long-term memory is full.");
    expect(w.emitted("done")).toBeUndefined();
  });
});
