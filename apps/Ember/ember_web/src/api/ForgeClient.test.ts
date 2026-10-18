import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { forgeClient } from "./ForgeClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("forgeClient", () => {
  it("reads and sets the plan allowlists", async () => {
    await forgeClient.plans();
    await forgeClient.setPlans("claude", ["max", "pro"]);

    expect(request.mock.calls).toEqual([
      ["GET", "/api/forge/plans"],
      ["PUT", "/api/forge/plans/claude", { plans: ["max", "pro"] }],
    ]);
  });

  it("lists, creates and removes workers", async () => {
    await forgeClient.workers();
    await forgeClient.createWorker("codex", "codex");
    await forgeClient.removeWorker(5);

    expect(request.mock.calls).toEqual([
      ["GET", "/api/forge/workers"],
      ["POST", "/api/forge/workers", { provider: "codex", label: "codex" }],
      ["DELETE", "/api/forge/workers/5"],
    ]);
  });

  it("manages groups", async () => {
    await forgeClient.groups();
    await forgeClient.createGroup("Build", "plan");
    await forgeClient.updateGroup(3, { mode: "full_auto", confirm_full_auto: true });
    await forgeClient.removeGroup(3);

    expect(request.mock.calls).toEqual([
      ["GET", "/api/forge/groups"],
      ["POST", "/api/forge/groups", { title: "Build", mode: "plan" }],
      ["PATCH", "/api/forge/groups/3", { mode: "full_auto", confirm_full_auto: true }],
      ["DELETE", "/api/forge/groups/3"],
    ]);
  });

  it("invites and removes members", async () => {
    await forgeClient.invite(3, 7, "C:/site");
    await forgeClient.removeMember(3, 7);

    expect(request.mock.calls).toEqual([
      ["POST", "/api/forge/groups/3/workers", { worker_id: 7, folder: "C:/site" }],
      ["DELETE", "/api/forge/groups/3/workers/7"],
    ]);
  });

  it("sends messages, answers permissions and stops a turn", async () => {
    await forgeClient.send(3, "@claude hi");
    await forgeClient.answerPermission(3, "r1", false);
    await forgeClient.stop(3);

    expect(request.mock.calls).toEqual([
      ["POST", "/api/forge/groups/3/messages", { text: "@claude hi" }],
      ["POST", "/api/forge/groups/3/permissions/r1", { allow: false }],
      ["POST", "/api/forge/groups/3/cancel", {}],
    ]);
  });

  it("builds the event stream address", () => {
    expect(forgeClient.eventsUrl(3, 12)).toBe("/api/forge/groups/3/events?after=12");
  });
});


describe("forgeClient folders", () => {
  it("moves a member and opens the folder dialog on a worker", async () => {
    await forgeClient.setFolder(3, 5, "D:/other");
    await forgeClient.browseFolder(5, "C:/site");
    await forgeClient.browseFolder(5, "");

    expect(request.mock.calls).toEqual([
      ["PATCH", "/api/forge/groups/3/workers/5", { folder: "D:/other" }],
      ["POST", "/api/forge/workers/5/browse", { start: "C:/site" }],
      ["POST", "/api/forge/workers/5/browse", { start: null }],
    ]);
  });
});
