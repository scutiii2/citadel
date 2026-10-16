import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { notesClient } from "./NotesClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("notesClient", () => {
  it("lists notes", async () => {
    await notesClient.list();

    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/notes");
  });

  it("creates a note from a title and body", async () => {
    await notesClient.create("Groceries", "milk");

    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/notes", { title: "Groceries", body: "milk" });
  });

  it("replaces and deletes one note by id", async () => {
    await notesClient.update("abc", "Shopping", "milk, eggs");
    await notesClient.remove("abc");

    expect(request.mock.calls).toEqual([
      ["PUT", "/api/notes/abc", { title: "Shopping", body: "milk, eggs" }],
      ["DELETE", "/api/notes/abc"],
    ]);
  });

  it("encodes an id so it cannot change the path", async () => {
    await notesClient.remove("../admin");

    expect(request).toHaveBeenCalledExactlyOnceWith("DELETE", "/api/notes/..%2Fadmin");
  });
});
