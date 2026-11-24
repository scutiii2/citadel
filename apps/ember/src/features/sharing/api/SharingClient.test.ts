import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { sharingClient } from "./SharingClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("sharingClient", () => {
  it("creates a share for an account or for the global brain", async () => {
    await sharingClient.create({ kind: "file", file_id: "f1", recipient: "bo" });
    await sharingClient.create({ kind: "skill", skill_id: 3, to_global: true });
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/brain/shares", { kind: "file", file_id: "f1", recipient: "bo" });
    expect(request).toHaveBeenNthCalledWith(2, "POST", "/api/brain/shares", { kind: "skill", skill_id: 3, to_global: true });
  });

  it("lists the inbox and the sent shares as plain arrays", async () => {
    request.mockResolvedValueOnce({ shares: [{ id: "a" }] } as never).mockResolvedValueOnce({ shares: [{ id: "b" }] } as never);
    expect(await sharingClient.inbox()).toEqual([{ id: "a" }]);
    expect(await sharingClient.sent()).toEqual([{ id: "b" }]);
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/shares/inbox");
    expect(request).toHaveBeenNthCalledWith(2, "GET", "/api/brain/shares/sent");
  });

  it("reads, withdraws and declines one share", async () => {
    await sharingClient.get("s-1");
    await sharingClient.revoke("s-1");
    await sharingClient.decline("s-1");
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/shares/s-1");
    expect(request).toHaveBeenNthCalledWith(2, "DELETE", "/api/brain/shares/s-1");
    expect(request).toHaveBeenNthCalledWith(3, "POST", "/api/brain/shares/s-1/decline");
  });

  it("accepts with the title and folder the person chose, or with nothing", async () => {
    await sharingClient.accept("s-1", { title: "Tea", folder: "shared" });
    await sharingClient.accept("s-1");
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/brain/shares/s-1/accept", { title: "Tea", folder: "shared" });
    expect(request).toHaveBeenNthCalledWith(2, "POST", "/api/brain/shares/s-1/accept", {});
  });

  it("lists, adds and removes blocks", async () => {
    request.mockResolvedValueOnce({ blocks: [{ uid: "u1" }] } as never).mockResolvedValueOnce({ blocks: [{ uid: "u2" }] } as never);
    expect(await sharingClient.blocks()).toEqual([{ uid: "u1" }]);
    expect(await sharingClient.block("bo")).toEqual([{ uid: "u2" }]);
    await sharingClient.unblock("u/2");
    expect(request).toHaveBeenNthCalledWith(1, "GET", "/api/brain/blocks");
    expect(request).toHaveBeenNthCalledWith(2, "PUT", "/api/brain/blocks", { username: "bo" });
    expect(request).toHaveBeenNthCalledWith(3, "DELETE", "/api/brain/blocks/u%2F2");
  });

  it("encodes a share id", async () => {
    await sharingClient.get("a/b");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/brain/shares/a%2Fb");
  });
});
