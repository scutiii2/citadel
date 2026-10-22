import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";
import TagInput from "./TagInput.vue";

const normalize = (raw: string) =>
  raw.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9_-]/g, "").slice(0, 30);
const KNOWN = [
  { tag: "movies", count: 3 },
  { tag: "money", count: 2 },
  { tag: "work", count: 1 },
];

let wrapper: VueWrapper | null = null;
afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

/** Mounts the box with the model held by a parent, as NotesView holds it. */
function setup(initial: string[] = [], props: Record<string, unknown> = {}) {
  const tags = ref(initial);
  const text = ref("");
  const field = ref<InstanceType<typeof TagInput> | null>(null);
  const Host = defineComponent({
    setup: () => () =>
      h(TagInput, {
        ref: field,
        modelValue: tags.value,
        "onUpdate:modelValue": (v: string[]) => (tags.value = v),
        text: text.value,
        "onUpdate:text": (v: string) => (text.value = v),
        known: KNOWN,
        normalize,
        max: 3,
        maxLength: 30,
        ...props,
      }),
  });
  wrapper = mount(Host, { attachTo: document.body });
  return { w: wrapper, tags, text, field };
}

const box = (w: VueWrapper) => w.get("input[aria-label='Add a tag']");
const names = (w: VueWrapper) => w.findAll("[role=option] .name").map((o) => o.text());
const chips = (w: VueWrapper) => w.findAll("ul[aria-label='Tags'] li").map((li) => li.text().replace("×", "").trim());
const listbox = (w: VueWrapper) => w.get("[role=listbox]");
const visible = (w: VueWrapper) => (listbox(w).element as HTMLElement).style.display !== "none";
const key = (w: VueWrapper, k: string) => box(w).trigger("keydown", { key: k });

describe("TagInput", () => {
  it("is a combobox that points at its list", async () => {
    const { w } = setup();
    expect(box(w).attributes("role")).toBe("combobox");
    expect(box(w).attributes("aria-expanded")).toBe("false");

    await box(w).trigger("focus");

    expect(box(w).attributes("aria-expanded")).toBe("true");
    expect(box(w).attributes("aria-controls")).toBe(listbox(w).attributes("id"));
  });

  it("opens its list on focus with the known tags, most used first, with counts", async () => {
    const { w } = setup();
    expect(visible(w)).toBe(false);

    await box(w).trigger("focus");

    expect(visible(w)).toBe(true);
    expect(names(w)).toEqual(["movies", "money", "work"]);
    expect(w.findAll("[role=option] .count").map((c) => c.text())).toEqual(["3 notes", "2 notes", "1 note"]);
  });

  it("leaves out tags already chosen and filters by what is typed", async () => {
    const { w } = setup(["work"]);
    await box(w).trigger("focus");
    expect(names(w)).toEqual(["movies", "money"]);

    await box(w).setValue("mon");

    expect(names(w)).toEqual(["money"]);
    await box(w).setValue("zzz");
    expect(visible(w)).toBe(false); // nothing to offer: no empty box
  });

  it("matches what is typed with spaces as the tag it would become", async () => {
    const { w } = setup([], { known: [{ tag: "work-stuff", count: 1 }] });
    await box(w).trigger("focus");

    await box(w).setValue("work st");

    expect(names(w)).toEqual(["work-stuff"]);
  });

  it("walks the list with the arrow keys, wrapping round, and Enter takes the highlighted tag", async () => {
    const { w, tags } = setup();
    await box(w).trigger("focus");
    const active = () => w.findAll("[role=option]").findIndex((o) => o.attributes("aria-selected") === "true");

    await key(w, "ArrowDown");
    expect(active()).toBe(0);
    expect(box(w).attributes("aria-activedescendant")).toBe(w.findAll("[role=option]")[0]!.attributes("id"));
    await key(w, "ArrowDown");
    await key(w, "ArrowDown");
    expect(active()).toBe(2);
    await key(w, "ArrowDown");
    expect(active()).toBe(0);
    await key(w, "ArrowUp");
    expect(active()).toBe(2);
    await key(w, "Enter");

    expect(tags.value).toEqual(["work"]);
    expect(names(w)).toEqual(["movies", "money"]); // taken tags leave the list
  });

  it("ArrowDown opens a closed list; Esc closes it and does not leave the page", async () => {
    const { w } = setup();
    await box(w).trigger("focus");
    const esc = new KeyboardEvent("keydown", { key: "Escape", cancelable: true, bubbles: true });
    let reachedParent = false;
    w.element.addEventListener("keydown", () => (reachedParent = true));

    box(w).element.dispatchEvent(esc);
    await w.vm.$nextTick();

    expect(visible(w)).toBe(false);
    expect(esc.defaultPrevented).toBe(true);
    expect(reachedParent).toBe(false);
    await key(w, "ArrowDown");
    expect(visible(w)).toBe(true);
  });

  it("Esc with the list closed is left alone, so a dialog around it can still close", async () => {
    const { w } = setup([], { known: [] });
    const esc = new KeyboardEvent("keydown", { key: "Escape", cancelable: true, bubbles: true });

    box(w).element.dispatchEvent(esc);

    expect(esc.defaultPrevented).toBe(false);
  });

  it("clicking an option adds it without taking focus from the box", async () => {
    const { w, tags } = setup();
    await box(w).trigger("focus");
    const mousedown = new MouseEvent("mousedown", { cancelable: true, bubbles: true });

    w.findAll("[role=option]")[1]!.element.dispatchEvent(mousedown);
    await w.vm.$nextTick();

    expect(mousedown.defaultPrevented).toBe(true); // the box keeps focus, so it does not blur first
    expect(tags.value).toEqual(["money"]);
  });

  it("Enter with nothing highlighted adds what is typed, cleaned, and never submits a form", async () => {
    const { w, tags, text } = setup();
    await box(w).setValue("  Work Stuff ");
    const enter = new KeyboardEvent("keydown", { key: "Enter", cancelable: true, bubbles: true });

    box(w).element.dispatchEvent(enter);
    await w.vm.$nextTick();

    expect(enter.defaultPrevented).toBe(true);
    expect(tags.value).toEqual(["work-stuff"]);
    expect(text.value).toBe("");
  });

  it("a comma adds what is typed, a repeat is not added twice, and blur adds what is left", async () => {
    const { w, tags } = setup();
    await box(w).setValue("home");
    await key(w, ",");
    await box(w).setValue("HOME");
    await key(w, "Enter");
    await box(w).setValue("later");
    await box(w).trigger("blur");

    expect(tags.value).toEqual(["home", "later"]);
    expect(visible(w)).toBe(false); // blur closes the list
  });

  it("removes a tag with its button and the last one with Backspace in an empty box", async () => {
    const { w, tags } = setup(["a", "b", "c"]);

    await w.get("button[aria-label='Remove tag b']").trigger("click");
    expect(chips(w)).toEqual(["a", "c"]);
    await key(w, "Backspace");
    expect(tags.value).toEqual(["a"]);
    await box(w).setValue("x");
    await key(w, "Backspace"); // text in the box: Backspace edits the text, not the chips
    expect(tags.value).toEqual(["a"]);
  });

  it("refuses a tag past the limit and keeps the text", async () => {
    const { w, tags, text } = setup(["a", "b", "c"]);

    await box(w).setValue("d");
    await key(w, "Enter");

    expect(w.get("[role=alert]").text()).toBe("A note can have at most 3 tags.");
    expect(tags.value).toEqual(["a", "b", "c"]);
    expect(text.value).toBe("d");
    await w.get("button[aria-label='Remove tag c']").trigger("click");
    expect(w.find("[role=alert]").exists()).toBe(false);
  });

  it("says so when nothing usable is left of what was typed", async () => {
    const { w, tags, text } = setup();

    await box(w).setValue("!!!");
    await key(w, "Enter");

    expect(w.get("[role=alert]").text()).toBe("A tag needs letters or digits.");
    expect(tags.value).toEqual([]);
    expect(text.value).toBe("");
  });

  it("lets the owner commit what is typed and add a tag from outside", async () => {
    const { w, tags, text, field } = setup();
    await box(w).setValue("typed");

    field.value!.commit();
    expect(field.value!.add("picked")).toBe(true);
    expect(field.value!.add("picked")).toBe(true); // already there
    await w.vm.$nextTick();

    expect(tags.value).toEqual(["typed", "picked"]);
    expect(text.value).toBe("");
    tags.value = ["a", "b", "c"]; // the owner replaced the tags (opened another note)
    await w.vm.$nextTick();
    expect(field.value!.add("d")).toBe(false);
  });

  it("does nothing while disabled", async () => {
    const { w } = setup(["a"], { disabled: true });

    expect(box(w).attributes("disabled")).toBeDefined();
    expect(w.get("button[aria-label='Remove tag a']").attributes("disabled")).toBeDefined();
    await box(w).trigger("focus");
    expect(visible(w)).toBe(false);
  });
});
