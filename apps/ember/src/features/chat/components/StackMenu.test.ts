import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { stackClient, type StackItem, type StackView } from "../api/StackClient";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import { useStackStore } from "../stores/stack";
import StackMenu from "./StackMenu.vue";

vi.mock("../api/StackClient", () => ({
  stackClient: { view: vi.fn(), add: vi.fn(), setPinned: vi.fn(), remove: vi.fn(), compact: vi.fn() },
}));

const client = vi.mocked(stackClient);
const item = (id: number, text: string, pinned = false): StackItem => ({ id, text, pinned, source: "agent", at: "2026-01-01T00:00:00Z" });
const view = (items: StackItem[], extra: Partial<StackView> = {}): StackView => ({ items, used: items.length, limit: 40, warn: false, full: false, ...extra });

const mounted: ReturnType<typeof mount>[] = [];

async function mountMenu(props: { chatId: string | null; locked?: boolean } = { chatId: "c-1" }) {
  setActivePinia(createPinia());
  useAuthStore().account = makeAccount({ username: "u", email: "u@example.com" });
  const w = mount(StackMenu, { props: { locked: false, ...props }, attachTo: document.body });
  mounted.push(w);
  await flushPromises();
  return w;
}

beforeEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = "";
  client.view.mockResolvedValue(view([item(1, "I live in Paris"), item(2, "Never email Bo", true)]));
});

afterEach(() => {
  for (const w of mounted.splice(0)) w.unmount();
});

describe("StackMenu", () => {
  it("keeps the panel open on a press inside it", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    w.get("[data-test=stack-panel]").element.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await w.vm.$nextTick();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(true);
  });

  it("drops the open panel and its draft on sign-out", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    await w.get("[data-test=add-text]").setValue("draft");
    useAuthStore().account = null;
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
    expect(useStackStore().entry("c-1").view).toBeNull();
  });


  it("renders nothing without a chat", async () => {
    const w = await mountMenu({ chatId: null });
    expect(w.find("[data-test=stack-button]").exists()).toBe(false);
    expect(client.view).not.toHaveBeenCalled();
  });

  it("loads the chat's stack and shows the count on the button", async () => {
    const w = await mountMenu();
    expect(client.view).toHaveBeenCalledWith("c-1");
    expect(w.get("[data-test=stack-button]").text()).toContain("Memory");
    expect(w.get("[data-test=stack-button]").text()).toContain("2/40");
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
  });

  it("says nearly full and full in words on the closed button", async () => {
    client.view.mockResolvedValue(view([item(1, "a")], { warn: true }));
    expect((await mountMenu()).get("[data-test=stack-button]").text()).toContain("nearly full");
    client.view.mockResolvedValue(view([item(1, "a")], { warn: true, full: true }));
    expect((await mountMenu()).get("[data-test=stack-button]").text()).toContain("full");
  });

  it("opens the panel, refreshes, and closes on Escape with focus back on the button", async () => {
    const w = await mountMenu();
    client.view.mockClear();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    expect(w.get("[data-test=stack-button]").attributes("aria-expanded")).toBe("true");
    expect(w.find("[data-test=stack-panel]").exists()).toBe(true);
    expect(client.view).toHaveBeenCalledTimes(1);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
    expect(document.activeElement).toBe(w.get("[data-test=stack-button]").element);
  });

  it("closes on a press outside", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await flushPromises();
    expect(w.find("[data-test=stack-panel]").exists()).toBe(false);
  });

  it("the panel's actions go through the store and show the server's list", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    client.setPinned.mockResolvedValue(item(1, "x", true));
    client.view.mockResolvedValue(view([item(1, "I live in Paris", true), item(2, "Never email Bo", true)]));
    await w.findAll("[data-test=pin]")[0]!.trigger("click");
    await flushPromises();
    expect(client.setPinned).toHaveBeenCalledWith("c-1", 1, true);
    expect(w.findAll("[data-test=pin]")[0]!.attributes("aria-pressed")).toBe("true");
    client.add.mockResolvedValue(item(3, "new"));
    client.view.mockResolvedValue(view([item(1, "a"), item(3, "new")]));
    await w.get("[data-test=add-text]").setValue("new");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(client.add).toHaveBeenCalledWith("c-1", "new");
    expect((w.get("[data-test=add-text]").element as HTMLTextAreaElement).value).toBe("");
  });

  it("a refused add keeps the text and shows the reason", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    client.add.mockRejectedValue(new ApiError(422, "An item holds at most 500 characters."));
    await w.get("[data-test=add-text]").setValue("too long");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(w.get("[data-test=add-error]").text()).toContain("at most 500");
    expect((w.get("[data-test=add-text]").element as HTMLTextAreaElement).value).toBe("too long");
  });

  it("Compact is off while an answer is written, and the list reloads when the answer ends", async () => {
    const w = await mountMenu({ chatId: "c-1", locked: true });
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    expect(w.get("[data-test=compact]").attributes("disabled")).toBeDefined();
    client.view.mockClear();
    client.view.mockResolvedValue(view([item(1, "saved by the agent during the answer")]));
    await w.setProps({ locked: false });
    await flushPromises();
    expect(client.view).toHaveBeenCalledTimes(1);
    expect(w.text()).toContain("saved by the agent during the answer");
    expect(w.get("[data-test=compact]").attributes("disabled")).toBeUndefined();
  });

  it("compacts through the store and shows the result", async () => {
    const w = await mountMenu();
    await w.get("[data-test=stack-button]").trigger("click");
    await flushPromises();
    client.compact.mockResolvedValue({ ...view([item(9, "summary")]), compacted: true, replaced: 1 });
    await w.get("[data-test=compact]").trigger("click");
    await flushPromises();
    expect(client.compact).toHaveBeenCalledWith("c-1");
    expect(w.text()).toContain("Replaced 1 item with a summary.");
  });

  it("another chat shows its own memory and drops the old one", async () => {
    const w = await mountMenu();
    const store = useStackStore();
    client.view.mockResolvedValue(view([item(7, "other chat")]));
    await w.setProps({ chatId: "c-2" });
    await flushPromises();
    expect(client.view).toHaveBeenLastCalledWith("c-2");
    expect(store.entry("c-1").view).toBeNull();
  });

  it("forgets the chat when it goes away", async () => {
    const w = await mountMenu();
    const store = useStackStore();
    mounted.splice(mounted.indexOf(w), 1);
    w.unmount();
    expect(store.entry("c-1").view).toBeNull();
  });
});
