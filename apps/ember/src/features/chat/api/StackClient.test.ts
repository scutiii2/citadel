import { beforeEach, describe, expect, it, vi } from "vitest";
import { stackClient } from "./StackClient";
import { apiRequest } from "../../../api/http";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("stackClient", () => {
  it("reads a chat's stack", async () => {
    await stackClient.view("c-1");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/chats/c-1/stack");
  });

  it("adds an item, pinned only when asked", async () => {
    await stackClient.add("c-1", "I live in Paris");
    await stackClient.add("c-1", "Never email Bo", true);
    expect(request).toHaveBeenNthCalledWith(1, "POST", "/api/chats/c-1/stack/items", { text: "I live in Paris", pinned: false });
    expect(request).toHaveBeenNthCalledWith(2, "POST", "/api/chats/c-1/stack/items", { text: "Never email Bo", pinned: true });
  });

  it("pins, unpins and removes one item", async () => {
    await stackClient.setPinned("c-1", 3, true);
    await stackClient.setPinned("c-1", 3, false);
    await stackClient.remove("c-1", 3);
    expect(request).toHaveBeenNthCalledWith(1, "PUT", "/api/chats/c-1/stack/items/3", { pinned: true });
    expect(request).toHaveBeenNthCalledWith(2, "PUT", "/api/chats/c-1/stack/items/3", { pinned: false });
    expect(request).toHaveBeenNthCalledWith(3, "DELETE", "/api/chats/c-1/stack/items/3");
  });

  it("compacts with a bodiless POST", async () => {
    await stackClient.compact("c-1");
    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/chats/c-1/stack/compact");
  });

  it("encodes a chat id so it cannot change the path", async () => {
    await stackClient.view("a/../b");
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/chats/a%2F..%2Fb/stack");
  });
});
