import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Account } from "../api/AuthClient";

const account = (permissions: string[]): Account => ({ id: 1, username: "a", email: "a@x", email_verified: true, roles: [], permissions });

// The router and the auth store's one-shot /me load are module singletons: load fresh ones per test.
async function freshRouter(permissions: string[]) {
  vi.resetModules();
  setActivePinia(createPinia());
  const { authClient } = await import("../api/AuthClient");
  vi.spyOn(authClient, "me").mockResolvedValue(account(permissions));
  return (await import("./index")).router;
}

beforeEach(() => vi.restoreAllMocks());

describe("router", () => {
  it("opens /capabilities for an account with capabilities.manage", async () => {
    const router = await freshRouter(["capabilities.manage"]);
    await router.push("/capabilities");
    expect(router.currentRoute.value.name).toBe("capabilities");
  });
  it("sends an account without the permission to no-access", async () => {
    const router = await freshRouter([]);
    await router.push("/capabilities");
    expect(router.currentRoute.value.name).toBe("no-access");
  });
});
