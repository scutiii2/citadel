import { afterEach, beforeEach, expect, it, vi } from "vitest";

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }));
vi.mock("../http", () => ({ apiRequest }));

import { authClient } from "./AuthClient";
import { sessionToken } from "../../utils/server";

const input = { username: "ada", email: "ada@example.com", password: "a-long-password", invite_code: "CODE" };
const registered = { account: { id: 1, username: "ada" }, verification_email_sent: true, email_error: null };

function desktop(on: boolean): void {
  if (on) vi.stubGlobal("__TAURI_INTERNALS__", {});
  else delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
}

beforeEach(() => { apiRequest.mockReset(); localStorage.clear(); localStorage.setItem("ember.server_url", "http://10.0.0.5:29601"); });
afterEach(() => { desktop(false); localStorage.clear(); vi.unstubAllGlobals(); });

it("in the Windows app, registering also logs in so the app holds a session token", async () => {
  desktop(true);
  apiRequest.mockResolvedValueOnce(registered).mockResolvedValueOnce({ id: 1, username: "ada", session_token: "tok-1" });
  expect(await authClient.register(input)).toEqual(registered);
  expect(apiRequest).toHaveBeenLastCalledWith("POST", "/api/auth/login", { username: "ada", password: "a-long-password" }, { "X-Ember-Client": "desktop" });
  expect(sessionToken()).toBe("tok-1");
});

it("still returns the registration when that login fails", async () => {
  desktop(true);
  apiRequest.mockResolvedValueOnce(registered).mockRejectedValueOnce(new Error("boom"));
  expect(await authClient.register(input)).toEqual(registered);
});

it("in the browser, registering makes one call and no login", async () => {
  apiRequest.mockResolvedValueOnce(registered);
  await authClient.register(input);
  expect(apiRequest).toHaveBeenCalledOnce();
});
