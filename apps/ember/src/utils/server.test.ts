import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, authHeaders, credentialsMode, hasServer, normalizeServerUrl, publicOrigin, setServerBase, setSessionToken } from "./server";

function desktop(on: boolean): void {
  if (on) vi.stubGlobal("__TAURI_INTERNALS__", {});
  else delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
}

afterEach(() => { desktop(false); localStorage.clear(); vi.unstubAllGlobals(); });

describe("server in the browser", () => {
  it("uses the same origin and the cookie", () => {
    expect(apiUrl("/api/x")).toBe("/api/x");
    expect(authHeaders()).toEqual({});
    expect(credentialsMode()).toBe("same-origin");
    expect(hasServer()).toBe(true);
    expect(publicOrigin()).toBe(window.location.origin);
  });
});

describe("server in the Windows app", () => {
  it("needs a server before it can call", () => {
    desktop(true);
    expect(hasServer()).toBe(false);
    expect(setServerBase("ftp://x")).toBe(false);
    expect(setServerBase("http://10.0.0.5:29601/ignored")).toBe(true);
    expect(hasServer()).toBe(true);
    expect(apiUrl("/api/x")).toBe("http://10.0.0.5:29601/api/x");
    expect(publicOrigin()).toBe("http://10.0.0.5:29601");
  });

  it("sends the token as a bearer and no cookie", () => {
    desktop(true);
    setSessionToken("abc");
    expect(authHeaders()).toEqual({ Authorization: "Bearer abc" });
    expect(credentialsMode()).toBe("omit");
    setSessionToken("");
    expect(authHeaders()).toEqual({});
  });
});

it("normalizes server URLs", () => {
  expect(normalizeServerUrl(" https://a.example/path ")).toBe("https://a.example");
  expect(normalizeServerUrl("nope")).toBeNull();
});
