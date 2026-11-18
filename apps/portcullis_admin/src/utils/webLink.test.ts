import { describe, expect, it } from "vitest";
import { emberWebUrl } from "./webLink";
describe("emberWebUrl", () => {
  it("uses the same host and default ember_web port", () => {
    expect(emberWebUrl("http://127.0.0.1:26501/accounts?q=1#row", "")).toBe("http://127.0.0.1:26502/overview");
  });
  it("supports a configured deployment URL or proxy path", () => {
    expect(emberWebUrl("https://admin.example/accounts", "https://ember.example/")).toBe("https://ember.example/");
    expect(emberWebUrl("https://admin.example/accounts", "/web/")).toBe("https://admin.example/web/");
  });
});

it("falls back safely for invalid or non-HTTP deployment addresses", () => {
  expect(emberWebUrl("http://localhost:26501/", "http://[")).toBe("http://localhost:26502/overview");
  expect(emberWebUrl("http://localhost:26501/", "javascript:alert(1)")).toBe("http://localhost:26502/overview");
});
