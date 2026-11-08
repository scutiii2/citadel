import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authClient, type Account } from "../api/AuthClient";
import { useAuthStore } from "./auth";

const base: Account = { id: 1, username: "a", email: "a@x", email_verified: true, roles: [], permissions: ["agents.manage"] };

beforeEach(() => setActivePinia(createPinia()));

describe("auth store", () => {
  it("grants a held permission", async () => {
    vi.spyOn(authClient, "me").mockResolvedValue(base);
    const auth = useAuthStore();
    await auth.ensureLoaded();
    expect(auth.hasPermission("agents.manage")).toBe(true);
    expect(auth.hasPermission("other.thing")).toBe(false);
  });
  it("grants nothing while the email is unverified and verification is required", async () => {
    vi.spyOn(authClient, "me").mockResolvedValue({ ...base, email_verified: false });
    const auth = useAuthStore();
    await auth.ensureLoaded();
    expect(auth.hasPermission("agents.manage")).toBe(false);
  });
  it("is signed out when /me fails", async () => {
    vi.spyOn(authClient, "me").mockRejectedValue(new Error("down"));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const auth = useAuthStore();
    await auth.ensureLoaded();
    expect(auth.account).toBeNull();
  });
});
