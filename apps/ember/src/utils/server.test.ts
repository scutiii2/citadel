import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, authHeaders, checkServer, connectServer, credentialsMode, ensureServer, hasServer, isServerReady, normalizeServerUrl, onServerLost, publicOrigin, reportServerLost, saveFile, serverBase, serverError, setServerBase, setSessionToken } from "./server";

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

describe("server check in the Windows app", () => {
  const answer = (status: number, body: unknown) => vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });

  it("rejects a bad address without calling the network", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const result = await checkServer("not a url");
    expect(result.ok).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("saves the address only after the server answers", async () => {
    desktop(true);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const down = await connectServer("http://10.0.0.5:29601");
    expect(down).toMatchObject({ ok: false });
    expect(serverBase()).toBe("");
    expect(isServerReady()).toBe(false);
    expect(serverError()).toContain("Could not reach http://10.0.0.5:29601");

    vi.stubGlobal("fetch", answer(200, { status: "ok" }));
    const up = await connectServer("http://10.0.0.5:29601/ignored");
    expect(up).toEqual({ ok: true, origin: "http://10.0.0.5:29601" });
    expect(serverBase()).toBe("http://10.0.0.5:29601");
    expect(isServerReady()).toBe(true);
    expect(serverError()).toBe("");
  });

  it("refuses an address that answers but is not Ember", async () => {
    vi.stubGlobal("fetch", answer(200, { hello: "world" }));
    expect(await checkServer("http://10.0.0.5:80")).toMatchObject({ ok: false });
    vi.stubGlobal("fetch", answer(404, null));
    expect(await checkServer("http://10.0.0.5:80")).toMatchObject({ ok: false });
  });

  it("checks a saved address on launch and goes back to unready when the server is lost", async () => {
    desktop(true);
    setServerBase("http://10.0.0.6:29601");       // another origin than the one verified above
    expect(isServerReady()).toBe(false);          // saved, not yet answered in this run
    vi.stubGlobal("fetch", answer(200, { status: "ok" }));
    expect(await ensureServer()).toBe(true);
    const lost = vi.fn();
    onServerLost(lost);
    reportServerLost();
    expect(isServerReady()).toBe(false);
    expect(lost).toHaveBeenCalledOnce();
    reportServerLost();                            // only once per loss
    expect(lost).toHaveBeenCalledOnce();
  });

  it("is always ready in the browser", async () => {
    expect(isServerReady()).toBe(true);
    expect(await ensureServer()).toBe(true);
  });
});
