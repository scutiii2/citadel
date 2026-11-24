import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { BrainFileRow, SearchHit } from "../api/BrainClient";
import FileList from "./FileList.vue";

const row = (id: string, title: string, extra: Partial<BrainFileRow> = {}): BrainFileRow => ({
  id, title, folder: "", tags: [], source: "manual", last_editor: "user", agent_editable: false, edited: false, revision: 1,
  created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00", chars: 5, warning: null, shared_from: "", ...extra,
});

function mountList(props: Record<string, unknown> = {}) {
  const wrapper = mount(FileList, {
    props: {
      rows: [row("a", "Tea notes", { folder: "food", tags: ["tea"] }), row("b", "Plan", { source: "automatic" })],
      folders: ["food"], selectedId: null, draftTitle: null, isSearch: false, searchBusy: false, searchError: "", disabled: false,
      query: "", folder: null,
      "onUpdate:query": (value: string) => wrapper.setProps({ query: value }),
      "onUpdate:folder": (value: string | null) => wrapper.setProps({ folder: value }),
      ...props,
    },
  });
  return wrapper;
}

const rowsOf = (w: ReturnType<typeof mountList>) => w.findAll("ul[aria-label='Files'] li");

describe("FileList", () => {
  it("lists the rows with folder, tags and an agent mark", () => {
    const w = mountList();
    expect(rowsOf(w)).toHaveLength(2);
    expect(rowsOf(w)[0]!.text()).toContain("Tea notes");
    expect(rowsOf(w)[0]!.text()).toContain("food");
    expect(rowsOf(w)[0]!.text()).toContain("tea");
    expect(rowsOf(w)[1]!.text()).toContain("Agent file");
  });

  it("marks shared, edited and agent-editable files", () => {
    const w = mountList({ rows: [row("a", "S", { source: "shared", shared_from: "bo", edited: true }), row("b", "E", { agent_editable: true })] });
    expect(rowsOf(w)[0]!.text()).toContain("Shared by bo");
    expect(rowsOf(w)[0]!.text()).toContain("Edited");
    expect(rowsOf(w)[1]!.text()).toContain("Agents can edit");
  });

  it("selecting a row says which", async () => {
    const w = mountList();
    await w.get('[data-file-id="b"]').trigger("click");
    expect(w.emitted("select")).toEqual([["b"]]);
  });

  it("marks the open row and shows an unsaved new file first", () => {
    const w = mountList({ selectedId: "a", draftTitle: "" });
    expect(rowsOf(w)[0]!.text()).toContain("New file");
    expect(rowsOf(w)[0]!.text()).toContain("Not saved yet");
    expect(w.get('[data-file-id="a"]').attributes("aria-current")).toBe("true");
  });

  it("folder buttons set the folder and say which is pressed", async () => {
    const w = mountList();
    const group = w.get('[role="group"][aria-label="Folders"]');
    const buttons = group.findAll("button");
    expect(buttons.map((b) => b.text())).toEqual(["All", "No folder", "food"]);
    expect(buttons[0]!.attributes("aria-pressed")).toBe("true");
    await buttons[2]!.trigger("click");
    expect(w.emitted("update:folder")![0]).toEqual(["food"]);
    expect(w.findAll('[aria-label="Folders"] button')[2]!.attributes("aria-pressed")).toBe("true");
    await w.findAll('[aria-label="Folders"] button')[1]!.trigger("click");
    expect(w.emitted("update:folder")![1]).toEqual([""]);
  });

  it("has no folder buttons without folders, or while showing search results", () => {
    expect(mountList({ folders: [] }).find('[aria-label="Folders"]').exists()).toBe(false);
    expect(mountList({ isSearch: true }).find('[aria-label="Folders"]').exists()).toBe(false);
  });

  it("typing in the search box updates the query", async () => {
    const w = mountList();
    await w.get('input[aria-label="Search files"]').setValue("tea");
    expect(w.emitted("update:query")![0]).toEqual(["tea"]);
  });

  it("shows search results with their snippet", () => {
    const hit: SearchHit = { ...row("a", "Tea notes"), score: 2, snippet: "green tea steeps" };
    const w = mountList({ rows: [hit], isSearch: true });
    expect(w.text()).toContain("Search results");
    expect(rowsOf(w)[0]!.text()).toContain("green tea steeps");
  });

  it("explains an empty list and an empty search", () => {
    expect(mountList({ rows: [] }).text()).toContain("No files here yet.");
    const searched = mountList({ rows: [], isSearch: true });
    expect(searched.text()).toContain("No files match your search.");
  });

  it("shows a search that is running and one that failed", () => {
    expect(mountList({ searchBusy: true }).get('[role="status"]').text()).toContain("Searching");
    expect(mountList({ searchError: "Invalid brain request." }).get('[role="alert"]').text()).toBe("Invalid brain request.");
  });

  it("disables the rows while a change is running", () => {
    const w = mountList({ disabled: true });
    expect(w.get('[data-file-id="a"]').attributes("disabled")).toBeDefined();
  });
});
