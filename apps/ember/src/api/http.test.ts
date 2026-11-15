import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";

const ok = () => ({ status: 200, ok: true, statusText: "OK", json: async () => ({ ok: true }) }) as unknown as Response;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiRequest", () => {
  it("sends extra headers beside the JSON content type", async () => {
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) => ok());
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("POST", "/api/example/items", undefined, { "Idempotency-Key": "k-1" });

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/example/items", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Idempotency-Key": "k-1", "Content-Type": "application/json" },
      body: "{}",
    });
  });

  it("sends no headers and no body on a plain GET", async () => {
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) => ok());
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest("GET", "/api/example/list");

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/example/list", { method: "GET", credentials: "same-origin" });
  });
});
