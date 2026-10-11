import { expect, it, vi } from "vitest";
import { GamesAdminClient } from "./GamesAdminClient";
import type { apiRequest } from "./http";
it("uses the game registry and mutation routes", async () => {
  const request = vi.fn().mockResolvedValueOnce({ games: [{ id: "ascension", enabled: true }] }).mockResolvedValue({});
  const client = new GamesAdminClient(request as typeof apiRequest);
  expect(await client.registry()).toEqual([{ id: "ascension", enabled: true }]);
  await client.register("http://localhost:8060"); await client.refresh("a b"); await client.deregister("a b");
  expect(request.mock.calls).toEqual([["GET", "/api/games/registry"], ["POST", "/api/games", { url: "http://localhost:8060" }], ["POST", "/api/games/a%20b/refresh"], ["DELETE", "/api/games/a%20b"]]);
});
