import { expect, it } from "vitest";
import { GameOrigins } from "./GameOrigins";
it("keeps the loopback defaults and accepts explicit production origins", () => {
  expect(new GameOrigins().frameSource()).toBe("http://127.0.0.1:* http://localhost:*");
  expect(new GameOrigins("https://games.example https://other.example:8060").frameSource()).toBe("https://games.example https://other.example:8060");
});
it.each(["*", "https://*.example", "https://a.example/path", "https://user@a.example", "https://a.example;", "https://a.example?x", "javascript:bad"])("rejects invalid CSP origin %s", raw => {
  expect(() => new GameOrigins(raw)).toThrow();
});
