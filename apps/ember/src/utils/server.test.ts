import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, authHeaders, credentialsMode, hasServer, normalizeServerUrl, publicOrigin, saveFile, setServerBase, setSessionToken } from "./server";

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

describe("saveFile", () => {
  it("leaves the link alone in the browser", async () => {
    const event = new Event("click", { cancelable: true });
    expect(await saveFile(event, "/api/files/a", "a.txt")).toBe("");
    expect(event.defaultPrevented).toBe(false);
  });

  it("fetches with the bearer and saves a blob in the Windows app", async () => {
    desktop(true);
    setServerBase("http://10.0.0.5:29601");
    setSessionToken("abc");
    const fetched = vi.fn(async () => new Response("data"));
    vi.stubGlobal("fetch", fetched);
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const event = new Event("click", { cancelable: true });

    expect(await saveFile(event, "/api/files/a", "a.txt")).toBe("");

    expect(event.defaultPrevented).toBe(true);
    expect(fetched).toHaveBeenCalledWith("http://10.0.0.5:29601/api/files/a", { credentials: "omit", headers: { Authorization: "Bearer abc" } });
    expect(clicked).toHaveBeenCalledOnce();
    clicked.mockRestore();
  });

  it("returns a message when the file is gone", async () => {
    desktop(true);
    setServerBase("http://10.0.0.5:29601");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    expect(await saveFile(new Event("click", { cancelable: true }), "/api/files/a", "a.txt")).toMatch(/could not be downloaded/);
  });
});
