import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ApprovalMode } from "../utils/approvalMode";
import ApprovalModePicker from "./ApprovalModePicker.vue";

let wrapper: VueWrapper | null = null;

const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  // jsdom does not implement <dialog>.showModal; give it the open flag the dialog reads.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
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
  document.body.innerHTML = "";
});

function setup(mode: ApprovalMode = "allow_all", forced = false) {
  wrapper = mount(ApprovalModePicker, { props: { mode, forced }, attachTo: document.body });
  return wrapper;
}

const chip = (w: VueWrapper) => w.get("button.mode-chip");
const menu = (w: VueWrapper) => w.find("[role=menu]");
const items = (w: VueWrapper) => w.findAll("[role=menuitemradio]");
const open = async (w: VueWrapper) => {
  await chip(w).trigger("click");
  await flushPromises();
};
const dialogButton = (which: "cancel" | "confirm") =>
  document.body.querySelector<HTMLButtonElement>(which === "cancel" ? "dialog[open] button.cancel" : "dialog[open] .confirm");

describe("ApprovalModePicker chip", () => {
  it.each([
    ["ask", "Ask every time"],
    ["auto", "Auto"],
    ["allow_all", "Allow all"],
  ] as const)("shows %s as %j", (mode, label) => {
    const w = setup(mode);

    expect(chip(w).text()).toBe(label);
    expect(menu(w).exists()).toBe(false);
  });

  it("opens a menu of the three modes with what each does, and marks the one in force", async () => {
    const w = setup("auto");

    await open(w);

    expect(chip(w).attributes("aria-expanded")).toBe("true");
    expect(items(w).map((i) => i.find(".name").text())).toEqual(["Ask every time", "Auto", "Allow all"]);
    expect(items(w).map((i) => i.attributes("aria-checked"))).toEqual(["false", "true", "false"]);
    expect(items(w)[0]!.text()).toContain("Every tool waits for your answer.");
    expect(items(w)[1]!.text()).toContain("Tools that only read run on their own.");
    expect(items(w)[2]!.text()).toContain("No tool asks first.");
  });

  it("puts focus on the mode in force when it opens", async () => {
    const w = setup("auto");

    await open(w);

    expect(document.activeElement).toBe(items(w)[1]!.element);
  });
});

describe("ApprovalModePicker choosing", () => {
  it("emits the choice and closes for Ask every time and Auto, with no confirmation", async () => {
    const w = setup("allow_all");
    await open(w);

    await items(w)[0]!.trigger("click");
    await flushPromises();

    expect(w.emitted("update:mode")).toEqual([["ask"]]);
    expect(menu(w).exists()).toBe(false);
    expect(document.body.querySelector("dialog[open]")).toBeNull();

    await open(w);
    await items(w)[1]!.trigger("click");
    expect(w.emitted("update:mode")).toEqual([["ask"], ["auto"]]);
  });

  it("choosing the mode already in force only closes the menu", async () => {
    const w = setup("auto");
    await open(w);

    await items(w)[1]!.trigger("click");
    await flushPromises();

    expect(w.emitted("update:mode")).toBeUndefined();
    expect(menu(w).exists()).toBe(false);
  });

  it("asks before Allow all, and Cancel changes nothing", async () => {
    const w = setup("ask");
    await open(w);

    await items(w)[2]!.trigger("click");
    await flushPromises();

    expect(w.emitted("update:mode")).toBeUndefined();
    expect(menu(w).exists()).toBe(false);
    const dialog = document.body.querySelector("dialog[open]");
    expect(dialog?.textContent).toContain("Allow every tool to run without asking?");
    expect(dialog?.textContent).toContain("change your notes");
    dialogButton("cancel")!.click();
    await flushPromises();

    expect(w.emitted("update:mode")).toBeUndefined();
    expect(chip(w).text()).toBe("Ask every time");
  });

  it("takes Allow all once it is confirmed", async () => {
    const w = setup("auto");
    await open(w);
    await items(w)[2]!.trigger("click");
    await flushPromises();

    dialogButton("confirm")!.click();
    await flushPromises();

    expect(w.emitted("update:mode")).toEqual([["allow_all"]]);
  });
});

describe("ApprovalModePicker keyboard", () => {
  it("arrow keys move between the modes, wrapping round", async () => {
    const w = setup("ask");
    await open(w);

    await menu(w).trigger("keydown", { key: "ArrowDown" });
    expect(document.activeElement).toBe(items(w)[1]!.element);
    await menu(w).trigger("keydown", { key: "ArrowDown" });
    await menu(w).trigger("keydown", { key: "ArrowDown" });
    expect(document.activeElement).toBe(items(w)[0]!.element);
    await menu(w).trigger("keydown", { key: "ArrowUp" });
    expect(document.activeElement).toBe(items(w)[2]!.element);
  });

  it("the numbers 1 to 3 pick a mode", async () => {
    const w = setup("allow_all");
    await open(w);

    await menu(w).trigger("keydown", { key: "2" });

    expect(w.emitted("update:mode")).toEqual([["auto"]]);
  });

  it("the number 3 still asks before Allow all", async () => {
    const w = setup("ask");
    await open(w);

    await menu(w).trigger("keydown", { key: "3" });
    await flushPromises();

    expect(w.emitted("update:mode")).toBeUndefined();
    expect(document.body.querySelector("dialog[open]")).not.toBeNull();
  });

  it("Escape closes the menu, gives focus back to the chip and does not reach what is around it", async () => {
    const w = setup("ask");
    await open(w);
    let reached = false;
    document.body.addEventListener("keydown", () => (reached = true), { once: true });
    const escape = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });

    menu(w).element.dispatchEvent(escape);
    await flushPromises();

    expect(menu(w).exists()).toBe(false);
    expect(document.activeElement).toBe(chip(w).element);
    expect(escape.defaultPrevented).toBe(true);
    expect(reached).toBe(false);
  });

  it("a click anywhere else closes the menu", async () => {
    const w = setup("ask");
    await open(w);

    document.body.click();
    await flushPromises();

    expect(menu(w).exists()).toBe(false);
  });

  it("clicking the chip again closes it", async () => {
    const w = setup("ask");
    await open(w);

    await chip(w).trigger("click");
    await flushPromises();

    expect(menu(w).exists()).toBe(false);
  });
});

describe("ApprovalModePicker while an administrator requires approval", () => {
  it("shows Ask every time, locked, whatever was saved", () => {
    const w = setup("allow_all", true);

    expect(chip(w).text()).toBe("Ask every time");
    expect(chip(w).find(".lock-icon").exists()).toBe(true);
    expect(chip(w).attributes("title")).toContain("administrator requires approval");
  });

  it("disables the other two modes, says why, and ignores clicks and keys on them", async () => {
    const w = setup("auto", true);
    await open(w);

    expect(items(w).map((i) => i.attributes("aria-disabled"))).toEqual(["false", "true", "true"]);
    expect(items(w).map((i) => i.attributes("aria-checked"))).toEqual(["true", "false", "false"]);
    expect(menu(w).text()).toContain("Your administrator requires approval before every tool.");
    await items(w)[1]!.trigger("click");
    await items(w)[2]!.trigger("click");
    await menu(w).trigger("keydown", { key: "2" });
    await menu(w).trigger("keydown", { key: "3" });
    await flushPromises();

    expect(w.emitted("update:mode")).toBeUndefined();
    expect(document.body.querySelector("dialog[open]")).toBeNull();
  });
});
