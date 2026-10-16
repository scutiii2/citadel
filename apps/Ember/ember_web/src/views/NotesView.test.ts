import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { ApiError } from "../api/http";
import { notesClient, type Note } from "../api/NotesClient";
import NotesView from "./NotesView.vue";

vi.mock("../api/NotesClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/NotesClient")>()),
  notesClient: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));

const client = vi.mocked(notesClient);
const note = (
  id: string, title: string, body = "", updated = "2026-01-01T00:00:00", tags: string[] = [], agent_readable = false,
): Note => ({ id, title, body, tags, agent_readable, created_at: updated, updated_at: updated });

let wrapper: VueWrapper | null = null;

async function setup(notes: Note[] = []) {
  client.list.mockResolvedValue(notes);
  wrapper = mount(NotesView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}

const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom does not implement <dialog>.showModal; give it the open flag the component reads.
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
});

const buttonByText = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text);
// The confirm button draws its label letter by letter, so it is found by class, not by text.
const dialogButton = (text: string) =>
  text === "Cancel"
    ? document.body.querySelector<HTMLButtonElement>("dialog[open] button.cancel")
    : document.body.querySelector<HTMLButtonElement>("dialog[open] .confirm");
const rows = (w: VueWrapper) => w.findAll("ul[aria-label='Notes'] li");

describe("NotesView", () => {
  it("says so when there are no notes", async () => {
    const w = await setup();

    expect(w.text()).toContain("You have no notes yet.");
    expect(w.text()).toContain("0/200 notes");
  });

  it("lists notes with a short preview", async () => {
    const w = await setup([note("a", "First", "line one\n\nline   two"), note("b", "Second")]);

    expect(rows(w)).toHaveLength(2);
    expect(rows(w)[0]!.text()).toContain("First");
    expect(rows(w)[0]!.text()).toContain("line one line two");
  });

  it("shows why the list could not load", async () => {
    client.list.mockRejectedValue(new ApiError(503, "Notes storage is unavailable"));
    wrapper = mount(NotesView);
    await flushPromises();

    expect(wrapper.find("[role=alert]").text()).toContain("Notes storage is unavailable");
    expect(wrapper.find(".layout").exists()).toBe(false);
  });

  it("creates a note: Save needs a title, and the note moves into the list", async () => {
    client.create.mockResolvedValue(note("n1", "Groceries", "milk"));
    const w = await setup();

    await buttonByText(w, "New note")!.trigger("click");
    const save = buttonByText(w, "Save")!;
    expect(save.attributes("disabled")).toBeDefined();
    await w.get("input[aria-label=Title]").setValue("  Groceries ");
    await w.get("textarea").setValue("milk");
    expect(save.attributes("disabled")).toBeUndefined();
    await w.get("form").trigger("submit");
    await flushPromises();

    expect(client.create).toHaveBeenCalledExactlyOnceWith({
      title: "Groceries", body: "milk", tags: [], agent_readable: false,
    });
    expect(rows(w)).toHaveLength(1);
    expect(w.text()).toContain("Saved.");
    expect(w.text()).not.toContain("Unsaved changes");
  });

  it("edits a note and moves it to the top", async () => {
    client.update.mockResolvedValue(note("b", "Second!", "x", "2026-02-01T00:00:00"));
    const w = await setup([note("a", "First", "", "2026-01-02T00:00:00"), note("b", "Second", "", "2026-01-01T00:00:00")]);

    await rows(w)[1]!.get("button").trigger("click");
    await w.get("input[aria-label=Title]").setValue("Second!");
    expect(w.text()).toContain("Unsaved changes");
    await w.get("textarea").setValue("x");
    await w.get("form").trigger("submit");
    await flushPromises();

    expect(client.update).toHaveBeenCalledExactlyOnceWith("b", {
      title: "Second!", body: "x", tags: [], agent_readable: false,
    });
    expect(rows(w)[0]!.text()).toContain("Second!");
    expect(w.text()).not.toContain("Unsaved changes");
  });

  it("shows the server's message when saving fails and keeps the draft", async () => {
    client.create.mockRejectedValue(new ApiError(409, "You can keep at most 200 notes"));
    const w = await setup();

    await buttonByText(w, "New note")!.trigger("click");
    await w.get("input[aria-label=Title]").setValue("x");
    await w.get("form").trigger("submit");
    await flushPromises();

    expect(w.get("form [role=alert]").text()).toBe("You can keep at most 200 notes");
    expect((w.get("input[aria-label=Title]").element as HTMLInputElement).value).toBe("x");
  });

  it("asks before dropping unsaved changes, and Cancel keeps them", async () => {
    const w = await setup([note("a", "First", "one"), note("b", "Second", "two")]);

    await rows(w)[0]!.get("button").trigger("click");
    await w.get("textarea").setValue("changed");
    await rows(w)[1]!.get("button").trigger("click");
    await flushPromises();

    expect(document.body.querySelector("dialog[open]")?.textContent).toContain("Discard your changes?");
    dialogButton("Cancel")!.click();
    await flushPromises();
    expect((w.get("textarea").element as HTMLTextAreaElement).value).toBe("changed");

    await rows(w)[1]!.get("button").trigger("click");
    dialogButton("Discard")!.click();
    await flushPromises();
    expect((w.get("textarea").element as HTMLTextAreaElement).value).toBe("two");
  });

  it("switches without asking when nothing changed", async () => {
    const w = await setup([note("a", "First", "one"), note("b", "Second", "two")]);

    await rows(w)[0]!.get("button").trigger("click");
    await rows(w)[1]!.get("button").trigger("click");

    expect(document.body.querySelector("dialog[open]")).toBeNull();
    expect((w.get("textarea").element as HTMLTextAreaElement).value).toBe("two");
  });

  it("deletes a note only after confirmation", async () => {
    client.remove.mockResolvedValue(undefined);
    const w = await setup([note("a", "First")]);

    await rows(w)[0]!.get("button").trigger("click");
    await buttonByText(w, "Delete this note")!.trigger("click");
    dialogButton("Cancel")!.click();
    await flushPromises();
    expect(client.remove).not.toHaveBeenCalled();

    await buttonByText(w, "Delete this note")!.trigger("click");
    dialogButton("Delete note")!.click();
    await flushPromises();

    expect(client.remove).toHaveBeenCalledExactlyOnceWith("a");
    expect(rows(w)).toHaveLength(0);
    expect(w.text()).toContain("Note deleted.");
  });

  it("refuses a new note at the limit without opening an editor", async () => {
    const full = Array.from({ length: 200 }, (_, i) => note(String(i), `N${i}`));
    const w = await setup(full);

    await buttonByText(w, "New note")!.trigger("click");

    expect(w.find("form").exists()).toBe(false);
    expect(w.text()).toContain("at most 200 notes");
  });
});

describe("NotesView tags", () => {
  const tagBox = (w: VueWrapper) => w.get("input[aria-label='Add a tag']");
  const chips = (w: VueWrapper) => w.findAll("ul[aria-label='Tags'] li").map((li) => li.text().replace("×", "").trim());

  it("adds tags with Enter or a comma, cleans them and drops repeats", async () => {
    const w = await setup([note("a", "First")]);
    await rows(w)[0]!.get("button").trigger("click");

    await tagBox(w).setValue("  Work Stuff ");
    await tagBox(w).trigger("keydown", { key: "Enter" });
    await tagBox(w).setValue("home");
    await tagBox(w).trigger("keydown", { key: "," });
    await tagBox(w).setValue("WORK-stuff");
    await tagBox(w).trigger("keydown", { key: "Enter" });

    expect(chips(w)).toEqual(["work-stuff", "home"]);
    expect((tagBox(w).element as HTMLInputElement).value).toBe("");
    expect(w.text()).toContain("Unsaved changes");
  });

  it("does not save the note when Enter is pressed in the tag box", async () => {
    const w = await setup([note("a", "First")]);
    await rows(w)[0]!.get("button").trigger("click");

    await tagBox(w).setValue("x");
    const event = new KeyboardEvent("keydown", { key: "Enter", cancelable: true });
    tagBox(w).element.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(client.update).not.toHaveBeenCalled();
  });

  it("removes a tag with its button and with Backspace in an empty box", async () => {
    const w = await setup([note("a", "First", "", "2026-01-01T00:00:00", ["a", "b", "c"])]);
    await rows(w)[0]!.get("button").trigger("click");

    await w.get("button[aria-label='Remove tag b']").trigger("click");
    expect(chips(w)).toEqual(["a", "c"]);
    await tagBox(w).trigger("keydown", { key: "Backspace" });
    expect(chips(w)).toEqual(["a"]);
  });

  it("refuses an 11th tag and a tag with nothing usable in it", async () => {
    const ten = Array.from({ length: 10 }, (_, i) => `t${i}`);
    const w = await setup([note("a", "First", "", "2026-01-01T00:00:00", ten)]);
    await rows(w)[0]!.get("button").trigger("click");

    await tagBox(w).setValue("one-more");
    await tagBox(w).trigger("keydown", { key: "Enter" });
    expect(w.get("[role=alert]").text()).toContain("at most 10 tags");
    expect(chips(w)).toHaveLength(10);

    await w.get("button[aria-label='Remove tag t0']").trigger("click");
    await tagBox(w).setValue("!!!");
    await tagBox(w).trigger("keydown", { key: "Enter" });
    expect(w.get("[role=alert]").text()).toContain("letters or digits");
  });

  it("offers the tags the account already uses, most used first, minus the ones on this note", async () => {
    const w = await setup([
      note("a", "A", "", "2026-01-03T00:00:00", ["work", "home"]),
      note("b", "B", "", "2026-01-02T00:00:00", ["home"]),
      note("c", "C", "", "2026-01-01T00:00:00", ["zeta"]),
    ]);
    await rows(w)[0]!.get("button").trigger("click");

    const options = w.findAll("datalist option").map((o) => o.attributes("value"));

    expect(options).toEqual(["zeta"]); // "work" and "home" are on the open note already
    await w.get("button[aria-label='Remove tag home']").trigger("click");
    expect(w.findAll("datalist option").map((o) => o.attributes("value"))).toEqual(["home", "zeta"]);
  });

  it("adds a tag still in the box when saving, and sends the tags", async () => {
    client.update.mockResolvedValue(note("a", "First", "", "2026-02-01T00:00:00", ["new"]));
    const w = await setup([note("a", "First")]);
    await rows(w)[0]!.get("button").trigger("click");

    await tagBox(w).setValue("New");
    expect(w.text()).toContain("Unsaved changes");
    await w.get("form").trigger("submit");
    await flushPromises();

    expect(client.update).toHaveBeenCalledExactlyOnceWith("a", {
      title: "First", body: "", tags: ["new"], agent_readable: false,
    });
    expect(chips(w)).toEqual(["new"]);
  });

  it("shows tags in the list", async () => {
    const w = await setup([note("a", "First", "", "2026-01-01T00:00:00", ["work", "home"])]);

    expect(rows(w)[0]!.findAll(".tag").map((t) => t.text())).toEqual(["work", "home"]);
  });
});

describe("NotesView agent access", () => {
  const warning = (w: VueWrapper) => w.find("[role=note]");
  const flag = (w: VueWrapper) => w.get("input[role=switch]");

  it("is off by default and shows no warning", async () => {
    const w = await setup();
    await buttonByText(w, "New note")!.trigger("click");

    expect((flag(w).element as HTMLInputElement).checked).toBe(false);
    expect(warning(w).exists()).toBe(false);
  });

  it("warns as soon as it is turned on, and the warning goes when it is turned off", async () => {
    const w = await setup();
    await buttonByText(w, "New note")!.trigger("click");

    await flag(w).setValue(true);

    expect(warning(w).text()).toContain("Agents can read this note");
    expect(warning(w).text()).toContain("do not store passwords");
    await flag(w).setValue(false);
    expect(warning(w).exists()).toBe(false);
  });

  it("counts as an unsaved change and is sent on save", async () => {
    client.update.mockResolvedValue(note("a", "First", "", "2026-02-01T00:00:00", [], true));
    const w = await setup([note("a", "First")]);
    await rows(w)[0]!.get("button").trigger("click");
    expect(w.text()).not.toContain("Unsaved changes");

    await flag(w).setValue(true);
    expect(w.text()).toContain("Unsaved changes");
    await w.get("form").trigger("submit");
    await flushPromises();

    expect(client.update).toHaveBeenCalledExactlyOnceWith("a", {
      title: "First", body: "", tags: [], agent_readable: true,
    });
    expect(rows(w)[0]!.text()).toContain("Agents can read");
    expect(w.text()).not.toContain("Unsaved changes");
  });

  it("opens a note that agents can read with the switch on and the warning showing", async () => {
    const w = await setup([note("a", "First", "", "2026-01-01T00:00:00", [], true)]);

    await rows(w)[0]!.get("button").trigger("click");

    expect((flag(w).element as HTMLInputElement).checked).toBe(true);
    expect(warning(w).exists()).toBe(true);
  });

  it("asks before leaving a note whose only change is the switch", async () => {
    const w = await setup([note("a", "First"), note("b", "Second")]);
    await rows(w)[0]!.get("button").trigger("click");
    await flag(w).setValue(true);

    await rows(w)[1]!.get("button").trigger("click");
    await flushPromises();

    expect(document.body.querySelector("dialog[open]")?.textContent).toContain("Discard your changes?");
  });
});

describe("NotesView leaving the page", () => {
  async function setupRouted(notes: Note[]) {
    client.list.mockResolvedValue(notes);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/notes", component: NotesView },
        { path: "/other", component: { template: "<p>other</p>" } },
      ],
    });
    await router.push("/notes");
    wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router] } });
    await flushPromises();
    return { w: wrapper, router };
  }

  it("leaves at once when nothing is unsaved", async () => {
    const { router } = await setupRouted([note("a", "First", "one")]);

    await router.push("/other");

    expect(router.currentRoute.value.path).toBe("/other");
    expect(document.body.querySelector("dialog[open]")).toBeNull();
  });

  it("asks first with unsaved edits; Cancel stays and Leave page goes", async () => {
    const { w, router } = await setupRouted([note("a", "First", "one")]);
    await w.findAll("ul[aria-label='Notes'] li")[0]!.get("button").trigger("click");
    await w.get("textarea").setValue("changed");

    const stay = router.push("/other");
    await flushPromises();
    expect(document.body.querySelector("dialog[open]")?.textContent).toContain("Leave without saving?");
    dialogButton("Cancel")!.click();
    await stay;
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/notes");
    expect((w.get("textarea").element as HTMLTextAreaElement).value).toBe("changed");

    const go = router.push("/other");
    await flushPromises();
    dialogButton("Leave page")!.click();
    await go;
    expect(router.currentRoute.value.path).toBe("/other");
  });

  it("warns on tab close or reload only while there are unsaved edits", async () => {
    const { w } = await setupRouted([note("a", "First", "one")]);
    const closing = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(closing()).toBe(false);

    await w.findAll("ul[aria-label='Notes'] li")[0]!.get("button").trigger("click");
    await w.get("textarea").setValue("changed");

    expect(closing()).toBe(true);
  });
});
