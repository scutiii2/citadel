import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/http";
import { notesClient, type Note } from "../api/NotesClient";
import NotesView from "./NotesView.vue";

vi.mock("../api/NotesClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/NotesClient")>()),
  notesClient: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));

const client = vi.mocked(notesClient);
const note = (id: string, title: string, body = "", updated = "2026-01-01T00:00:00"): Note => ({
  id, title, body, created_at: updated, updated_at: updated,
});

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

    expect(client.create).toHaveBeenCalledExactlyOnceWith("Groceries", "milk");
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

    expect(client.update).toHaveBeenCalledExactlyOnceWith("b", "Second!", "x");
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
