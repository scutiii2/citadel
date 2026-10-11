import { expect, it, vi } from "vitest";
import { GamesClient } from "./GamesClient";
import type { apiRequest } from "./http";
it("reads the catalog envelope and launches escaped game ids", async () => {
  const request = vi.fn().mockResolvedValueOnce({ games: [{ id: "ascension" }] }).mockResolvedValueOnce({ url: "http://localhost:8060/#ticket=x" });
  const client = new GamesClient(request as typeof apiRequest);
  expect(await client.list()).toEqual([{ id: "ascension" }]);
  expect(await client.launch("a b")).toEqual({ url: "http://localhost:8060/#ticket=x" });
  expect(request.mock.calls).toEqual([["GET", "/api/games"], ["POST", "/api/games/a%20b/launch"]]);
});
