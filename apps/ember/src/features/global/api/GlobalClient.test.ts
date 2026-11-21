import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { globalClient, GLOBAL_NOTICE } from "./GlobalClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));
const request = vi.mocked(apiRequest);

beforeEach(() => vi.clearAllMocks());

describe("globalClient", () => {
  it("reads files, one file, a search and the summary", async () => {
    request.mockResolvedValue({ files: [], folders: [], results: [] });
    await globalClient.list();
    await globalClient.list("team/docs");
    await globalClient.get("f".repeat(32));
    expect(await globalClient.search("tea party")).toEqual([]);
    await globalClient.summary();
    expect(request.mock.calls.map((c) => [c[0], c[1]])).toEqual([
      ["GET", "/api/brain/global/files"],
      ["GET", "/api/brain/global/files?folder=team%2Fdocs"],
      ["GET", `/api/brain/global/files/${"f".repeat(32)}`],
      ["GET", "/api/brain/global/search?q=tea%20party"],
      ["GET", "/api/brain/global/summary"],
    ]);
  });

  it("writes files with the opened revision", async () => {
    request.mockResolvedValue({});
    await globalClient.create({ title: "T", body: "b", folder: "" });
    await globalClient.update("a".repeat(32), { body: "new" }, 3);
    await globalClient.remove("a".repeat(32));
    expect(request.mock.calls).toEqual([
      ["POST", "/api/brain/global/files", { title: "T", body: "b", folder: "" }],
      ["PUT", `/api/brain/global/files/${"a".repeat(32)}`, { body: "new", expected_revision: 3 }],
      ["DELETE", `/api/brain/global/files/${"a".repeat(32)}`],
    ]);
  });

  it("reads active skills for everyone and every skill for a writer, and changes skills", async () => {
    request.mockResolvedValue([]);
    await globalClient.skills();
    await globalClient.allSkills();
    request.mockResolvedValue({});
    await globalClient.setSkillStatus(4, "active");
    await globalClient.updateSkill(4, { title: "t", when_to_use: "w", steps: "s", tools: "" });
    await globalClient.removeSkill(4);
    expect(request.mock.calls).toEqual([
      ["GET", "/api/brain/global/skills"],
      ["GET", "/api/brain/global/skills/all"],
      ["PUT", "/api/brain/global/skills/4/status", { status: "active" }],
      ["PUT", "/api/brain/global/skills/4", { title: "t", when_to_use: "w", steps: "s", tools: "" }],
      ["DELETE", "/api/brain/global/skills/4"],
    ]);
  });

  it("reads and answers the review queue", async () => {
    request.mockResolvedValueOnce({ shares: [{ id: "s1" }] });
    expect(await globalClient.queue()).toEqual([{ id: "s1" }]);
    request.mockResolvedValue({});
    await globalClient.share("s1");
    await globalClient.approve("s1", { title: "T", folder: "shared" });
    await globalClient.reject("s1");
    expect(request.mock.calls.slice(1)).toEqual([
      ["GET", "/api/brain/global/shares/s1"],
      ["POST", "/api/brain/global/shares/s1/approve", { title: "T", folder: "shared" }],
      ["POST", "/api/brain/global/shares/s1/reject"],
    ]);
  });

  it("carries the notice sentence", () => {
    expect(GLOBAL_NOTICE).toBe("Everyone on this instance, and every agent, can read this. Do not put private data here.");
  });
});
