import { describe, expect, it } from "vitest";
import { resolveGuard, type GuardAuth } from "./guard";

const holds = (...names: string[]): GuardAuth => ({ signedIn: true, hasPermission: (p) => names.includes(p) });
const plain = holds();
const anon: GuardAuth = { signedIn: false, hasPermission: () => false };
const firstPage = { name: "usage", fullPath: "/usage", permission: "usage.all.view" };

describe("resolveGuard", () => {
  it("sends a guest to login with a redirect back", () => {
    expect(resolveGuard(firstPage, anon)).toEqual({ name: "login", query: { redirect: "/usage" } });
  });
  it("lets a guest open the login page", () => {
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, anon)).toBe(true);
  });
  it("lets an account with the permission open the page", () => {
    expect(resolveGuard(firstPage, holds("usage.all.view"))).toBe(true);
  });
  it("sends an account without the permission to no-access", () => {
    expect(resolveGuard(firstPage, plain)).toEqual({ path: "/no-access" });
  });
  it("shows no-access to an account without any page permission", () => {
    expect(resolveGuard({ name: "no-access", fullPath: "/no-access" }, plain)).toBe(true);
  });
  it("moves an account off login and no-access to its first allowed page", () => {
    const only = holds("tickets.manage");
    const home = { path: "/tickets" };
    const first = holds("usage.all.view", "tickets.manage");
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, only)).toEqual(home);
    expect(resolveGuard({ name: "no-access", fullPath: "/no-access" }, first)).toEqual({ path: "/usage" });
  });
  it("opens usage settings for settings managers", () => {
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, holds("settings.manage")))
      .toEqual({ path: "/usage-settings" });
  });
});
