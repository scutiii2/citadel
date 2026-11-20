import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { brainClient, folderProblem, normalizeFolder, normalizeTag } from "./BrainClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("brainClient", () => {
  it("lists, reads and summarises", async () => {
    await brainClient.list();
    await brainClient.get("f-1");
    await brainClient.summary();
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/files");
    expect(request).toHaveBeenNthCalledWith(2, "GET", "/api/brain/files/f-1");
    expect(request).toHaveBeenNthCalledWith(3, "GET", "/api/brain/summary");
  });

  it("creates a file from a draft", async () => {
    const draft = { title: "Tea", body: "Green", tags: ["tea"], folder: "food" };
    await brainClient.create(draft);
    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/brain/files", draft);
  });

  it("changes a file and sends the revision the editor opened", async () => {
    await brainClient.update("f-1", { title: "New" }, 3);
    expect(request).toHaveBeenCalledExactlyOnceWith("PUT", "/api/brain/files/f-1", { title: "New", expected_revision: 3 });
  });

  it("sends no revision when none is given", async () => {
    await brainClient.update("f-1", { agent_editable: true });
    expect(request).toHaveBeenCalledExactlyOnceWith("PUT", "/api/brain/files/f-1", { agent_editable: true });
  });

  it("reverts with the revision, and deletes", async () => {
    await brainClient.revert("f-1", 4);
    await brainClient.remove("f-1");
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/brain/files/f-1/revert", { expected_revision: 4 });
    expect(request).toHaveBeenNthCalledWith(2, "DELETE", "/api/brain/files/f-1");
  });

  it("searches with the query encoded", async () => {
    await brainClient.search("a b&c");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/brain/search?q=a%20b%26c");
  });

  it("encodes a file id", async () => {
    await brainClient.get("a/b");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/brain/files/a%2Fb");
  });
});

describe("normalizeTag", () => {
  it("follows the server's rules", () => {
    expect(normalizeTag("  Work Stuff! ")).toBe("work-stuff");
    expect(normalizeTag("--x")).toBe("x");
    expect(normalizeTag("a".repeat(40))).toHaveLength(30);
    expect(normalizeTag("!!!")).toBe("");
  });
});

describe("folders", () => {
  it("normalizeFolder cleans what was typed", () => {
    expect(normalizeFolder("  Projects / Citadel Notes/ ")).toBe("projects/citadel-notes");
    expect(normalizeFolder("\\a\\b")).toBe("a/b");
    expect(normalizeFolder("a//b")).toBe("a/b");
    expect(normalizeFolder("///")).toBe("");
  });

  it("folderProblem accepts the top level and up to three levels", () => {
    expect(folderProblem("")).toBe("");
    expect(folderProblem("a")).toBe("");
    expect(folderProblem("a/b/c")).toBe("");
    expect(folderProblem("a-1/b_2")).toBe("");
  });

  it("folderProblem refuses a fourth level, a bad start and a long name", () => {
    for (const bad of ["a/b/c/d", "-a", "a/_b", "a/", "x".repeat(41)]) expect(folderProblem(bad)).not.toBe("");
  });
});
