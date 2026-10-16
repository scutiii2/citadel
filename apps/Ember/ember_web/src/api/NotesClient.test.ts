import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { normalizeTag, notesClient } from "./NotesClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

const draft = { title: "Groceries", body: "milk", tags: ["home"], agent_readable: true };

describe("notesClient", () => {
  it("lists notes", async () => {
    await notesClient.list();

    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/notes");
  });

  it("creates a note from a whole draft", async () => {
    await notesClient.create(draft);

    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/notes", draft);
  });

  it("replaces and deletes one note by id", async () => {
    await notesClient.update("abc", { ...draft, title: "Shopping", agent_readable: false });
    await notesClient.remove("abc");

    expect(request.mock.calls).toEqual([
      ["PUT", "/api/notes/abc", { title: "Shopping", body: "milk", tags: ["home"], agent_readable: false }],
      ["DELETE", "/api/notes/abc"],
    ]);
  });

  it("encodes an id so it cannot change the path", async () => {
    await notesClient.remove("../admin");

    expect(request).toHaveBeenCalledExactlyOnceWith("DELETE", "/api/notes/..%2Fadmin");
  });
});

describe("normalizeTag", () => {
  it.each([
    ["Work", "work"],
    ["  to do  list ", "to-do-list"],
    ["#Home!", "home"],
    ["_-lead", "lead"],
    ["ünï", "n"],
    ["a_b-c9", "a_b-c9"],
    ["   ", ""],
    ["!!!", ""],
    ["x".repeat(40), "x".repeat(30)],
  ])("turns %j into %j", (raw, tag) => {
    expect(normalizeTag(raw)).toBe(tag);
  });
});
