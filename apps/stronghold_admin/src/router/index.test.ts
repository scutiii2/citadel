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
  it("opens /usage for an account with usage.all.view", async () => {
    const router = await freshRouter(["usage.all.view"]);
    await router.push("/usage");
    expect(router.currentRoute.value.name).toBe("usage");
  });
  it("sends an account without the permission to no-access", async () => {
    const router = await freshRouter([]);
    await router.push("/usage");
    expect(router.currentRoute.value.name).toBe("no-access");
  });
  it("opens /brain-settings for an account with settings.manage", async () => {
    const router = await freshRouter(["settings.manage"]);
    await router.push("/brain-settings");
    expect(router.currentRoute.value.name).toBe("brain-settings");
  });
  it("gates Tool services on tool_services.manage, in the router and the nav list", async () => {
    const { STRONGHOLD_PAGES } = await import("./pages");
    expect(STRONGHOLD_PAGES.find((page) => page.label === "Tool services")?.permission).toBe("tool_services.manage");
    const router = await freshRouter([]);
    expect(router.resolve("/tool-services").meta.permission).toBe("tool_services.manage");
  });
  it("sends an account without settings.manage away from /brain-settings", async () => {
    const router = await freshRouter(["usage.all.view"]);
    expect(router.resolve("/brain-settings").meta.permission).toBe("settings.manage");
    await router.push("/brain-settings");
    expect(router.currentRoute.value.name).toBe("usage");
  });
});
