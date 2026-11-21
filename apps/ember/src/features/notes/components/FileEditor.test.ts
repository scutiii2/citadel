import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import FileEditor from "./FileEditor.vue";

const manual = { source: "manual", last_editor: "user", edited: false, warning: null, shared_from: "" } as const;
const MODELS = ["title", "body", "tags", "tagText", "folder", "agentEditable"] as const;

function mountEditor(props: Record<string, unknown> = {}) {
  const handlers = Object.fromEntries(MODELS.map((name) => [`onUpdate:${name}`, (value: unknown) => wrapper.setProps({ [name]: value })]));
  const wrapper = mount(FileEditor, {
    props: {
      title: "Tea", body: "Green", tags: [], tagText: "", folder: "", agentEditable: false,
      file: manual, folders: [], knownTags: [], maxChars: 20_000, folderProblem: "", canRevert: false, revertHint: "", disabled: false,
      canShare: true, shareHint: "",
      ...handlers, ...props,
    },
    attachTo: document.body,
  });
  return wrapper;
}

describe("FileEditor", () => {
  it("offers Share for a saved file and asks the page to open the dialog", async () => {
    const w = mountEditor();
    const button = w.findAll("button").find((b) => b.text() === "Share a copy…")!;
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(w.emitted("share")).toHaveLength(1);
  });

  it("keeps Share off, with the reason, until the file is saved and unchanged", () => {
    const w = mountEditor({ canShare: false, shareHint: "Save your changes first. A share sends the saved file." });
    expect(w.findAll("button").find((b) => b.text() === "Share a copy…")!.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("Save your changes first.");
    expect(mountEditor({ file: null }).text()).not.toContain("Share a copy…");
  });

  it("shows the title and the text with their limits", () => {
    const w = mountEditor({ maxChars: 500 });
    expect((w.get('input[aria-label="Title"]').element as HTMLInputElement).value).toBe("Tea");
    expect(w.get('input[aria-label="Title"]').attributes("maxlength")).toBe("200");
    expect((w.get('textarea[aria-label="File text"]').element as HTMLTextAreaElement).value).toBe("Green");
    expect(w.get('textarea[aria-label="File text"]').attributes("maxlength")).toBe("500");
  });

  it("typing updates the models", async () => {
    const w = mountEditor();
    await w.get('input[aria-label="Title"]').setValue("Coffee");
    await w.get('textarea[aria-label="File text"]').setValue("Black");
    expect(w.emitted("update:title")![0]).toEqual(["Coffee"]);
    expect(w.emitted("update:body")![0]).toEqual(["Black"]);
  });

  it("warns, in words, about an agent's file and offers no agent switch", () => {
    const w = mountEditor({ file: { ...manual, source: "automatic", last_editor: "agent", warning: "Written by an agent. Editing it may break the agent that uses it." } });
    expect(w.get('[data-test="agent-warning"]').text()).toContain("Editing it may break the agent that uses it.");
    expect(w.find('input[type="checkbox"]').exists()).toBe(false);
    expect(w.text()).toContain("An agent wrote this file, so agents can edit it.");
  });

  it("says who shared a shared file", () => {
    const w = mountEditor({ file: { ...manual, source: "shared", shared_from: "bo" } });
    expect(w.get('[data-test="shared-note"]').text()).toContain("Shared by bo");
  });

  it("says when an agent last changed a file the user wrote", () => {
    const w = mountEditor({ file: { ...manual, last_editor: "agent" } });
    expect(w.text()).toContain("An agent last changed this file.");
  });

  it("the agent switch updates the model, and the page says agents can read every file", async () => {
    const w = mountEditor();
    expect(w.text()).toContain("Agents can read every file here.");
    await w.get('input[type="checkbox"]').setValue(true);
    expect(w.emitted("update:agentEditable")![0]).toEqual([true]);
  });

  it("shows the folder problem", () => {
    const w = mountEditor({ folderProblem: "A folder is up to 3 levels." });
    expect(w.get('[role="alert"]').text()).toBe("A folder is up to 3 levels.");
  });

  it("typing a folder is kept as typed, and leaving the box cleans it", async () => {
    const w = mountEditor();
    const input = w.get('input[aria-label="Folder"]');
    await input.setValue("Projects / Citadel");
    expect(w.emitted("update:folder")![0]).toEqual(["Projects / Citadel"]);
    await input.trigger("blur");
    expect(w.emitted("update:folder")![1]).toEqual(["projects/citadel"]);
  });

  it("an existing folder can be picked", async () => {
    const w = mountEditor({ folders: ["food", "food/tea"] });
    await w.get('button[aria-label="Use folder food/tea"]').trigger("click");
    expect(w.emitted("update:folder")![0]).toEqual(["food/tea"]);
  });

  it("restore original is only there for an edited file, and waits for a clean editor", async () => {
    expect(mountEditor().text()).not.toContain("Restore original");
    const edited = { ...manual, source: "automatic", edited: true, warning: "w" } as const;
    const blocked = mountEditor({ file: edited, canRevert: false, revertHint: "Save or discard your changes first." });
    const button = blocked.findAll("button").find((b) => b.text() === "Restore original")!;
    expect(button.attributes("disabled")).toBeDefined();
    expect(blocked.text()).toContain("Save or discard your changes first.");
    const ready = mountEditor({ file: edited, canRevert: true });
    await ready.findAll("button").find((b) => b.text() === "Restore original")!.trigger("click");
    expect(ready.emitted("revert")).toHaveLength(1);
  });

  it("delete is offered for a saved file only", async () => {
    const saved = mountEditor();
    await saved.findAll("button").find((b) => b.text() === "Delete this file")!.trigger("click");
    expect(saved.emitted("remove")).toHaveLength(1);
    expect(mountEditor({ file: null }).text()).not.toContain("Delete this file");
  });

  it("offers agent editing after the file exists", () => {
    const draft = mountEditor({ file: null });
    expect(draft.find('[role="switch"]').exists()).toBe(false);
    expect(draft.text()).toContain("Agents can read every file here.");
  });

  it("disables the fields while a change is running", () => {
    const w = mountEditor({ disabled: true });
    expect(w.get('input[aria-label="Title"]').attributes("disabled")).toBeDefined();
    expect(w.get('textarea[aria-label="File text"]').attributes("disabled")).toBeDefined();
  });

  it("exposes commitTags and focusTitle", () => {
    const w = mountEditor();
    expect(typeof w.vm.commitTags).toBe("function");
    w.vm.focusTitle();
    expect(document.activeElement).toBe(w.get('input[aria-label="Title"]').element);
  });
});
