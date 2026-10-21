import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { brainsClient } from "../api/BrainsClient";
import BrainsView from "./BrainsView.vue";

const route = vi.hoisted(() => ({ query: {} as Record<string, string> }));
vi.mock("vue-router", () => ({ useRoute: () => route }));
vi.mock("../api/BrainsClient", () => ({ brainsClient: { browse: vi.fn() } }));
vi.mock("../components/BrainConnectionForm.vue", () => ({ default: { template: '<div>Personal connection form</div>' } }));
const client = vi.mocked(brainsClient);
const entries = [{ path: "Inbox", kind: "folder" }, { path: "Guide.md", kind: "file" }];
let wrapper: VueWrapper | undefined;
const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  vi.resetAllMocks();
  route.query = {};
  client.browse.mockResolvedValue({ entries });
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => {
  wrapper?.unmount();
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});
async function setup() {
  wrapper = mount(BrainsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
function button(w: VueWrapper, label: string) { return w.findAll("button").find(b => b.text() === label || b.attributes("aria-label") === label)!; }

describe("Brains workspace", () => {
  it("browses on entry and retains folders and the document after checking status", async () => {
    const w = await setup();
    expect(client.browse).toHaveBeenCalledWith("instance", "list", "", "");
    client.browse.mockResolvedValueOnce({ content: "# A useful guide" });
    await button(w, "Guide.md").trigger("click"); await flushPromises();
    expect(w.get(".document-content").text()).toContain("A useful guide");
    expect(w.get(".file-list").text()).toContain("Inbox");
    client.browse.mockResolvedValueOnce({ status: "connected", index_status: "ready" });
    await button(w, "Check connection").trigger("click"); await flushPromises();
    expect(w.get(".document-content").text()).toContain("A useful guide");
    expect(w.text()).toContain("connected");
  });
  it("clears old content when switching brains, even if the next brain fails", async () => {
    const w = await setup();
    client.browse.mockResolvedValueOnce({ content: "Instance-only document" });
    await button(w, "Guide.md").trigger("click"); await flushPromises();
    client.browse.mockRejectedValueOnce(new Error("Personal vault unavailable"));
    await button(w, "Personal").trigger("click"); await flushPromises();
    expect(w.text()).not.toContain("Instance-only document");
    expect(w.get("[role=alert]").text()).toContain("Personal vault unavailable");
    expect(client.browse).toHaveBeenLastCalledWith("personal", "list", "", "");
  });
  it("searches both brains, preserves partial failures, and opens a hit in its own scope", async () => {
    const w = await setup();
    await button(w, "Both brains").trigger("click");
    await w.get("input[type=search]").setValue("garden");
    client.browse.mockResolvedValueOnce({ hits: [{ scope: "personal", path: "Inbox/Garden.md", heading: "Garden plan", content: "Plant herbs", connection_label: "My vault", refresh_status: "ready" }], failures: [{ scope: "instance", message: "Shared vault offline" }], refreshing: true });
    await w.get("form.search-form").trigger("submit"); await flushPromises();
    expect(client.browse).toHaveBeenLastCalledWith("both", "search", "", "garden");
    expect(w.text()).toContain("Shared vault offline");
    expect(w.text()).toContain("Indexing is in progress");
    client.browse.mockResolvedValueOnce({ entries: [{ path: "Inbox/Garden.md", kind: "file" }] }).mockResolvedValueOnce({ content: "# Personal garden" });
    await button(w, "Garden plan").trigger("click"); await flushPromises();
    expect(client.browse).toHaveBeenLastCalledWith("personal", "read", "Inbox/Garden.md", "garden");
    expect(w.get(".document-content").text()).toContain("Personal garden");
    expect(w.get(".reader-audience").text()).toBe("Only you");
  });
  it("opens deep links with their parent folder and preserves empty documents", async () => {
    route.query = { scope: "personal", path: "Inbox/Empty.md" };
    client.browse.mockResolvedValueOnce({ entries: [{ path: "Inbox/Empty.md", kind: "file" }] }).mockResolvedValueOnce({ content: "" });
    const w = await setup();
    expect(client.browse).toHaveBeenNthCalledWith(1, "personal", "list", "Inbox", "");
    expect(client.browse).toHaveBeenNthCalledWith(2, "personal", "read", "Inbox/Empty.md", "");
    expect(w.text()).toContain("This document is empty.");
  });
  it("keeps the current document when another read fails and allows retry", async () => {
    const w = await setup();
    client.browse.mockResolvedValueOnce({ content: "Keep this document" });
    await button(w, "Guide.md").trigger("click"); await flushPromises();
    client.browse.mockRejectedValueOnce(new Error("Temporarily offline"));
    await button(w, "Guide.md").trigger("click"); await flushPromises();
    expect(w.get(".document-content").text()).toContain("Keep this document");
    client.browse.mockResolvedValueOnce({ content: "Recovered" });
    await button(w, "Try again").trigger("click"); await flushPromises();
    expect(w.get(".document-content").text()).toContain("Recovered");
  });
});
