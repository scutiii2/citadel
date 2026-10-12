import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { GamesClient, type GameInfo } from "../api/GamesClient";
import { useAuthStore } from "./auth";
import { useGamesStore } from "./games";
const game: GameInfo = { id: "ascension", name: "Ascension", description: "Collect", icon: "", wallpaper: "", symbols: [], version: "1", url: "http://localhost:8060" };
beforeEach(() => { setActivePinia(createPinia()); useAuthStore().account = { id: 1, username: "player", email: "p@example.com", email_verified: true, roles: [], permissions: [] }; });
afterEach(() => vi.restoreAllMocks());
it("loads playable games and holds the launch URL only until close", async () => {
  vi.spyOn(GamesClient.prototype, "list").mockResolvedValue([game]);
  vi.spyOn(GamesClient.prototype, "launch").mockResolvedValue({ url: game.url + "/#ticket=launch" });
  const save = vi.spyOn(Storage.prototype, "setItem");
  const s = useGamesStore(); await s.load(); await s.open(game.id);
  expect(s.games).toEqual([game]); expect(s.activeId).toBe(game.id); expect(s.launchUrl).toContain("#ticket=");
  s.close(); expect(s.launchUrl).toBe(""); expect(s.activeId).toBeNull(); expect(save).not.toHaveBeenCalled();
});
it("discards late launch responses when closed or the account changes", async () => {
  let finish!: (value: {url: string}) => void;
  vi.spyOn(GamesClient.prototype, "list").mockResolvedValue([game]);
  vi.spyOn(GamesClient.prototype, "launch").mockImplementation(() => new Promise(done => { finish = done; }));
  const s = useGamesStore(); await s.load(); const pending = s.open(game.id); s.close(); finish({ url: game.url }); await pending;
  expect(s.activeId).toBeNull(); expect(s.launchUrl).toBe("");
  const next = s.open(game.id); useAuthStore().account = null; await flushPromises(); finish({ url: game.url }); await next;
  expect(s.games).toEqual([]); expect(s.launchUrl).toBe("");
});
it("shows failures without retaining a ticket and ignores late lists from another account", async () => {
  vi.spyOn(GamesClient.prototype, "launch").mockRejectedValue(new Error("Cannot launch"));
  const s = useGamesStore(); await s.open(game.id); expect(s.error).toBe("Cannot launch"); expect(s.launchUrl).toBe("");
  let finish!: (games: GameInfo[]) => void;
  vi.spyOn(GamesClient.prototype, "list").mockImplementation(() => new Promise(done => { finish = done; }));
  const pending = s.load(); useAuthStore().account = null; await flushPromises(); finish([game]); await pending;
  expect(s.games).toEqual([]);
});

it("waits for a list already in flight before deciding whether games are available", async () => {
  let finish!: (games: GameInfo[]) => void;
  vi.spyOn(GamesClient.prototype, "list").mockImplementation(() => new Promise(done => { finish = done; }));
  const s = useGamesStore(); const loading = s.load(); let settled = false;
  const waiting = s.ensureLoaded().then(() => { settled = true; });
  await flushPromises(); expect(settled).toBe(false);
  finish([game]); await Promise.all([loading, waiting]); expect(s.games).toEqual([game]);
});
