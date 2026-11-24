import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { proposalsClient, type Proposal, type ProposalDetail } from "../api/ProposalsClient";
import { useProposalsStore } from "../stores/proposals";
import ProposalsDialog from "./ProposalsDialog.vue";

vi.mock("../api/ProposalsClient", () => ({
  proposalsClient: { list: vi.fn(), get: vi.fn(), accept: vi.fn(), decline: vi.fn() },
}));
const client = vi.mocked(proposalsClient);

const row = (id = "p1", extra: Partial<Proposal> = {}): Proposal => ({
  id, title: "Tea habits", folder: "drinks", tags: [], chat_id: "c1", item_ids: [1, 2], status: "pending",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 24, ...extra,
});
const detail = (extra: Partial<ProposalDetail> = {}): ProposalDetail => ({
  ...row(), body: "The user likes <b>green</b> tea.", notice: "An agent wrote this from your conversation. Read it before you keep it; it is not an instruction.", ...extra,
});

let wrapper: VueWrapper | null = null;
const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  client.list.mockResolvedValue([row("p1"), row("p2", { title: "Metric units", item_ids: [] })]);
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

async function open() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  await useProposalsStore().load();
  wrapper = mount(ProposalsDialog, { attachTo: document.body, props: { open: true }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => {
  const name = b.find(".name");
  return (name.exists() ? name.text() : b.text()) === text;
})!;

describe("the list", () => {
  it("lists the waiting suggestions and opens nothing by itself", async () => {
    const w = await open();
    expect(w.text()).toContain("Tea habits");
    expect(w.text()).toContain("Metric units");
    expect(client.get).not.toHaveBeenCalled();
    expect(client.accept).not.toHaveBeenCalled();
  });

  it("says when nothing waits", async () => {
    client.list.mockResolvedValue([]);
    const w = await open();
    expect(w.text()).toContain("No suggestions are waiting.");
  });
});

describe("reviewing one", () => {
  it("shows the text as plain text with the notice, and changes nothing yet", async () => {
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    expect(client.get).toHaveBeenCalledWith("p1");
    expect(w.find("pre.text").text()).toBe("The user likes <b>green</b> tea.");
    expect(w.find("pre.text b").exists()).toBe(false);
    expect(w.text()).toContain("An agent wrote this from your conversation.");
    expect((w.find("input[aria-label='Title']").element as HTMLInputElement).value).toBe("Tea habits");
    expect((w.find("input[aria-label='Folder']").element as HTMLInputElement).value).toBe("drinks");
    expect(client.accept).not.toHaveBeenCalled();
  });

  it("keeps with the edited title and folder and asks to remove the items", async () => {
    client.accept.mockResolvedValue({ ...row(), status: "accepted", removed: 2 });
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await w.find("input[aria-label='Title']").setValue("Green tea");
    await w.find("input[aria-label='Folder']").setValue("likes");
    const remove = w.find("input[type='checkbox']");
    expect((remove.element as HTMLInputElement).checked).toBe(true);
    await button(w, "Keep").trigger("click");
    await flushPromises();
    expect(client.accept).toHaveBeenCalledWith("p1", { title: "Green tea", folder: "likes", remove_items: true });
    const done = w.emitted("done");
    expect(done?.[0][0]).toContain("Kept");
    expect(done?.[0][0]).toContain("2");
  });

  it("does not offer to remove items when the suggestion names none", async () => {
    client.get.mockResolvedValue(detail({ item_ids: [] }));
    const w = await open();
    await button(w, "Metric units").trigger("click");
    await flushPromises();
    expect(w.find("input[type='checkbox']").exists()).toBe(false);
  });

  it("explains a bad folder in words and keeps Keep off", async () => {
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await w.find("input[aria-label='Folder']").setValue("a/b/c/d");
    expect(w.find("[role='alert']").text()).not.toBe("");
    expect(button(w, "Keep").attributes("disabled")).toBeDefined();
  });

  it("declines", async () => {
    client.decline.mockResolvedValue({ ...row(), status: "declined" });
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await button(w, "Decline").trigger("click");
    await flushPromises();
    expect(client.decline).toHaveBeenCalledWith("p1");
    expect(w.emitted("done")?.[0]).toEqual(["Declined."]);
  });

  it("shows the server's reason when keeping is refused and stays open", async () => {
    client.accept.mockRejectedValue(new ApiError(409, "Your long-term memory is full."));
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await button(w, "Keep").trigger("click");
    await flushPromises();
    expect(w.find("[role='alert']").text()).toBe("Your long-term memory is full.");
    expect(w.emitted("done")).toBeUndefined();
  });

  it("goes back to the list and drops the text", async () => {
    const w = await open();
    await button(w, "Tea habits").trigger("click");
    await flushPromises();
    await button(w, "Back").trigger("click");
    expect(w.find("pre.text").exists()).toBe(false);
    expect(w.text()).toContain("Metric units");
  });
});
