import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { memoryClient } from "./api/MemoryClient";
import MemoryView from "./MemoryView.vue";

vi.mock("./api/MemoryClient", () => ({
  MEMORY_MAX: 200, MEMORY_TEXT_MAX: 500,
  memoryClient: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));
const client = vi.mocked(memoryClient);
const note = (id = 1, text = "Likes coffee") => ({ id, text, created_at: "2026-10-18T00:00:00Z" });
let wrapper: VueWrapper;
const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  vi.resetAllMocks();
  client.list.mockResolvedValue([note()]);
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => {
  wrapper?.unmount();
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});
async function setup() { wrapper = mount(MemoryView, { attachTo: document.body }); await flushPromises(); return wrapper; }
const button = (text: string) => wrapper.findAll("button").find((b) => b.text() === text)!;

describe("MemoryView", () => {
  it("asks before switching the inline editor away from an unsaved memory", async () => {
    client.list.mockResolvedValue([note(2, "Likes tea"), note(1, "Likes coffee")]);
    await setup();
    await wrapper.get('button[aria-label="Edit memory 1"]').trigger('click');
    expect(wrapper.find('form.editor').exists()).toBe(true);
    await wrapper.get('textarea').setValue('An unsaved correction');
    await wrapper.get('button[aria-label="Edit memory 2"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('textarea').element.value).toBe('An unsaved correction');
    const dialog = wrapper.get('dialog[aria-label="Discard your changes?"]');
    await dialog.get('button.cancel').trigger('click');
    await wrapper.get('button[aria-label="Edit memory 2"]').trigger('click');
    await dialog.get('button.confirm').trigger('click');
    await flushPromises();
    expect(wrapper.get('textarea').element.value).toBe('Likes tea');
    expect(client.update).not.toHaveBeenCalled();
  });

  it("keeps the saved memory selected and preserves drafts while filtering or clicking the current row", async () => {
    await setup();
    const row = wrapper.get('button[aria-label="Edit memory 1"]');
    await row.trigger('click');
    await wrapper.get('textarea').setValue('A correction');
    await row.trigger('click');
    expect(wrapper.get('textarea').element.value).toBe('A correction');
    await wrapper.get('input[type=search]').setValue('unrelated');
    expect(wrapper.get('textarea').element.value).toBe('A correction');
    client.update.mockResolvedValue(note(1, 'A correction'));
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>('form.editor textarea').element.value).toBe('A correction');
    expect(wrapper.get('button[aria-label="Edit memory 1"]').attributes('aria-current')).toBe('true');
    expect(button('Save').attributes('disabled')).toBeDefined();
  });
  it("lists saved memory and filters by text without a model call", async () => {
    await setup();
    expect(wrapper.text()).toContain("Likes coffee");
    expect(wrapper.text()).not.toContain("Invalid Date");
    await wrapper.get("input[type=search]").setValue("tea");
    expect(wrapper.text()).not.toContain("Likes coffee");
    expect(wrapper.text()).toContain("No memories match your search.");
  });
  it("paginates and resets the visible limit when searching", async () => {
    client.list.mockResolvedValue(Array.from({ length: 25 }, (_, i) => note(i + 1, `Fact ${i + 1}`)));
    await setup();
    expect(wrapper.findAll("article")).toHaveLength(20);
    await button("Load more").trigger("click");
    expect(wrapper.findAll("article")).toHaveLength(25);
    await wrapper.get("input[type=search]").setValue("Fact");
    expect(wrapper.findAll("article")).toHaveLength(20);
  });
  it("creates a memory, keeping the draft after an upstream error", async () => {
    await setup();
    await button("Add memory").trigger("click");
    await wrapper.get("textarea").setValue("Likes tea");
    client.create.mockRejectedValueOnce(new Error("Storage unavailable"));
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get("textarea").element.value).toBe("Likes tea");
    expect(wrapper.text()).toContain("Storage unavailable");
    client.create.mockResolvedValue(note(2, "Likes tea"));
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.findAll("article")).toHaveLength(2);
  });
  it("edits with the original text as a concurrency check", async () => {
    await setup();
    await wrapper.get('article button').trigger("click");
    await wrapper.get("textarea").setValue("Likes tea");
    client.update.mockResolvedValue(note(1, "Likes tea"));
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(client.update).toHaveBeenCalledWith(1, "Likes tea", "Likes coffee");
    expect(wrapper.findAll("article")[0]!.text()).toContain("Likes tea");
  });
  it("deletes only after confirmation", async () => {
    await setup();
    expect(wrapper.findAll("article button")).toHaveLength(1);
    await wrapper.get('article button').trigger("click");
    await button("Delete memory").trigger("click");
    expect(client.remove).not.toHaveBeenCalled();
    client.remove.mockResolvedValue();
    const confirm = document.body.querySelector<HTMLButtonElement>("dialog[open] .confirm")!;
    confirm.click(); await flushPromises();
    expect(client.remove).toHaveBeenCalledWith(1);
    expect(wrapper.text()).toContain("No saved memories yet.");
    expect(wrapper.find("form.editor").exists()).toBe(false);
  });
  it("keeps the editor draft when deletion is cancelled", async () => {
    await setup();
    await wrapper.get('article button').trigger("click");
    await wrapper.get("textarea").setValue("A corrected preference");
    await button("Delete memory").trigger("click");
    document.body.querySelector<HTMLButtonElement>("dialog[aria-label='Delete this memory?'] .cancel")!.click();
    await flushPromises();
    expect(wrapper.get("textarea").element.value).toBe("A corrected preference");
    expect(wrapper.find("form.editor").exists()).toBe(true);
    expect(client.remove).not.toHaveBeenCalled();
  });
  it("shows a recoverable loading failure", async () => {
    client.list.mockRejectedValueOnce(new Error("Offline"));
    await setup();
    expect(wrapper.get("[role=alert]").text()).toContain("Offline");
    await button("Try again").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("Likes coffee");
  });
  it("retains a stale edit and the original expected text after a conflict", async () => {
    await setup();
    await wrapper.get('article button').trigger("click");
    await wrapper.get("textarea").setValue("Likes tea");
    client.update.mockRejectedValue(new Error("This memory changed. Reload and try again."));
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.get("textarea").element.value).toBe("Likes tea");
    expect(wrapper.get("[role=alert]").text()).toContain("This memory changed");
    expect(wrapper.findAll("article")[0]!.text()).toContain("Likes coffee");
  });
  it("asks before discarding a memory draft", async () => {
    await setup();
    await button("Add memory").trigger("click");
    await wrapper.get("textarea").setValue("A draft");
    await wrapper.get("form button[type=button]").trigger("click"); await flushPromises();
    expect(document.body.querySelector("dialog[open][aria-label='Discard your changes?']")).not.toBeNull();
    expect(wrapper.get("textarea").element.value).toBe("A draft");
    document.body.querySelector<HTMLButtonElement>("dialog[aria-label='Discard your changes?'] .cancel")!.click();
    await flushPromises();
    expect(wrapper.get("textarea").element.value).toBe("A draft");
  });
  it("keeps an edited memory beyond the first page visible when search clears", async () => {
    client.list.mockResolvedValue(Array.from({ length: 25 }, (_, i) => note(25 - i, i === 24 ? "Oldest memory" : `Fact ${25 - i}`)));
    await setup();
    await wrapper.get("input[type=search]").setValue("Oldest memory");
    await wrapper.get('article button').trigger("click");
    await wrapper.get("textarea").setValue("Changed fact");
    client.update.mockResolvedValue(note(1, "Changed fact"));
    await wrapper.get("form").trigger("submit"); await flushPromises();
    expect(wrapper.findAll("article").some((card) => card.text().includes("Changed fact"))).toBe(true);
    expect(wrapper.get<HTMLInputElement>("input[type=search]").element.value).toBe("");
  });
});
