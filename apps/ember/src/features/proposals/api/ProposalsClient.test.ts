import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { proposalsClient } from "./ProposalsClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));
const request = vi.mocked(apiRequest);

beforeEach(() => vi.clearAllMocks());

describe("proposalsClient", () => {
  it("lists the waiting suggestions", async () => {
    request.mockResolvedValue({ proposals: [{ id: "p1" }] });
    expect(await proposalsClient.list()).toEqual([{ id: "p1" }]);
    expect(request).toHaveBeenCalledWith("GET", "/api/brain/proposals");
  });

  it("reads one, keeps one and declines one", async () => {
    request.mockResolvedValue({ id: "p1" });
    await proposalsClient.get("p1");
    await proposalsClient.accept("p1", { title: "T", folder: "f", remove_items: true });
    await proposalsClient.decline("p1");
    expect(request.mock.calls).toEqual([
      ["GET", "/api/brain/proposals/p1"],
      ["POST", "/api/brain/proposals/p1/accept", { title: "T", folder: "f", remove_items: true }],
      ["POST", "/api/brain/proposals/p1/decline"],
    ]);
  });
});
