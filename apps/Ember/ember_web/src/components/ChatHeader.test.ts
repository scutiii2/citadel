import { useAuthStore } from "../stores/auth";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatHeader from "./ChatHeader.vue";

// The agent tag talks to ember_api; the header only needs it to be there.
vi.mock("./EntryAgentTag.vue", () => ({ default: { template: '<div class="agent-tag">Talking to Test Agent</div>' } }));

type Props = InstanceType<typeof ChatHeader>["$props"];

function mountHeader(props: Partial<Props> = {}) {
  return mount(ChatHeader, {
    props: { title: "Usage page", hasMessages: true, contextPercent: 38, locked: false, ...props },
    attachTo: document.body,
  });
}

const iconButton = (w: ReturnType<typeof mountHeader>, label: string) =>
  w.findAll("button.action").find((b) => b.text() === label)!;
const menuItem = (label: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("[role='menuitem']")].find((b) => b.textContent?.trim() === label)!;

beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "a@example.com", email_verified: true, roles: [], permissions: ["chat.share"] };
  document.body.innerHTML = "";
});

describe("ChatHeader", () => {
  it("shows the title and the agent it talks to", () => {
    const w = mountHeader();

    expect(w.get("h2.title").text()).toBe("Usage page");
    expect(w.text()).toContain("Talking to Test Agent");
  });

  it("shows the context meter, and marks it high from 50%", () => {
    const w = mountHeader({ contextPercent: 38 });
    expect(w.get(".context").text()).toContain("38%");
    expect(w.get(".meter").attributes("aria-valuenow")).toBe("38");
    expect(w.get(".context").classes()).not.toContain("high");

    const high = mountHeader({ contextPercent: 62 });
    expect(high.get(".context").classes()).toContain("high");
  });

  describe("the context panel", () => {
    const BREAKDOWN = {
      tokens: 30_000,
      window: 100_000,
      parts: [
        { id: "system_prompt", label: "System prompt", tokens: 5_000 },
        { id: "messages", label: "Messages", tokens: 25_000 },
      ],
    };
    const panel = () => document.querySelector("[data-test=context-panel]");

    it("is plain text without a breakdown", async () => {
      const w = mountHeader();

      expect(w.find("button.context").exists()).toBe(false);
      await w.get(".context").trigger("click");
      expect(panel()).toBeNull();
    });

    it("opens from the meter and shows the parts", async () => {
      const w = mountHeader({ breakdown: BREAKDOWN });
      expect(w.get("button.context").attributes("aria-expanded")).toBe("false");

      await w.get("button.context").trigger("click");

      expect(w.get("button.context").attributes("aria-expanded")).toBe("true");
      expect(panel()?.textContent).toContain("System prompt");
      expect(panel()?.textContent).toContain("Free space");
    });

    it("passes the accuracy to the panel and on to its owner", async () => {
      const w = mountHeader({ breakdown: BREAKDOWN, accuracy: "estimate" });
      await w.get("button.context").trigger("click");

      const exact = [...document.querySelectorAll<HTMLButtonElement>("[data-test=context-accuracy] button")].find(
        (b) => b.textContent?.trim() === "Exact",
      )!;
      exact.click();
      await w.vm.$nextTick();

      expect(w.emitted("update:accuracy")).toEqual([["exact"]]);
      expect(panel()).not.toBeNull(); // a press inside the panel keeps it open
    });

    it("tells the panel whether the parts are exact", async () => {
      const w = mountHeader({ breakdown: { ...BREAKDOWN, exact: true } });

      await w.get("button.context").trigger("click");

      expect(panel()?.textContent).toContain("Counted by the model provider");
    });

    it("closes with a second click, Esc, or a press outside", async () => {
      const w = mountHeader({ breakdown: BREAKDOWN });

      await w.get("button.context").trigger("click");
      await w.get("button.context").trigger("click");
      expect(panel()).toBeNull();

      await w.get("button.context").trigger("click");
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      await w.vm.$nextTick();
      expect(panel()).toBeNull();

      await w.get("button.context").trigger("click");
      document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
      await w.vm.$nextTick();
      expect(panel()).toBeNull();
    });

    it("stays open for a press inside the panel", async () => {
      const w = mountHeader({ breakdown: BREAKDOWN });
      await w.get("button.context").trigger("click");

      panel()!.dispatchEvent(new Event("pointerdown", { bubbles: true }));
      await w.vm.$nextTick();

      expect(panel()).not.toBeNull();
    });

    it("closes when the breakdown goes away", async () => {
      const w = mountHeader({ breakdown: BREAKDOWN });
      await w.get("button.context").trigger("click");

      await w.setProps({ breakdown: null });

      expect(panel()).toBeNull();
      expect(w.find("button.context").exists()).toBe(false);
    });
  });

  it("leaves out the meter before any answer", () => {
    expect(mountHeader({ contextPercent: null }).find(".context").exists()).toBe(false);
  });

  it("leaves out the actions while the chat has no messages", () => {
    const w = mountHeader({ hasMessages: false });

    expect(w.findAll("button.action")).toHaveLength(0);
  });

  it("emits export and share from its icon buttons", async () => {
    const w = mountHeader();

    await iconButton(w, "Export").trigger("click");
    await iconButton(w, "Share").trigger("click");

    expect(w.emitted("export")).toHaveLength(1);
    expect(w.emitted("share")).toHaveLength(1);
  });

  it("opens a menu with Summarize and Clear, and emits the one chosen", async () => {
    const w = mountHeader();
    expect(iconButton(w, "More").attributes("aria-expanded")).toBe("false");

    await iconButton(w, "More").trigger("click");
    expect(iconButton(w, "More").attributes("aria-expanded")).toBe("true");
    expect(menuItem("Summarize")).toBeTruthy();

    menuItem("Clear").click();
    await w.vm.$nextTick();

    expect(w.emitted("clear")).toHaveLength(1);
    expect(w.emitted("summarize")).toBeUndefined();
    expect(document.querySelector("[role='menu']")).toBeNull();
  });

  it("closes the menu with a second press on the button", async () => {
    const w = mountHeader();

    await iconButton(w, "More").trigger("click");
    await iconButton(w, "More").trigger("click");

    expect(document.querySelector("[role='menu']")).toBeNull();
  });

  it("switches Summarize and Clear off while an answer is being written", async () => {
    const w = mountHeader({ locked: true });

    await iconButton(w, "More").trigger("click");

    expect(menuItem("Summarize").getAttribute("aria-disabled")).toBe("true");
    expect(menuItem("Clear").getAttribute("aria-disabled")).toBe("true");
    menuItem("Clear").click();
    expect(w.emitted("clear")).toBeUndefined();
  });
});

it("does not offer public sharing without chat.share", () => {
  useAuthStore().account!.permissions = [];
  expect(iconButton(mountHeader(), "Share")).toBeUndefined();
});
