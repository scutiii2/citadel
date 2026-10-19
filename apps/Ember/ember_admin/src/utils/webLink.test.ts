import { describe, expect, it } from "vitest";
import { emberWebUrl } from "./webLink";
describe("emberWebUrl", () => {
  it("uses the same host and default ember_web port", () => {
    expect(emberWebUrl("http://127.0.0.1:5176/accounts?q=1#row", "")).toBe("http://127.0.0.1:5173/overview");
  });
  it("supports a configured deployment URL or proxy path", () => {
    expect(emberWebUrl("https://admin.example/accounts", "https://ember.example/")).toBe("https://ember.example/");
    expect(emberWebUrl("https://admin.example/accounts", "/web/")).toBe("https://admin.example/web/");
  });
});

it("falls back safely for invalid or non-HTTP deployment addresses", () => {
  expect(emberWebUrl("http://localhost:5176/", "http://[")).toBe("http://localhost:5173/overview");
  expect(emberWebUrl("http://localhost:5176/", "javascript:alert(1)")).toBe("http://localhost:5173/overview");
});
