import { describe, expect, it } from "vitest";
import { resolveGuard, type GuardAuth } from "./guard";

const admin: GuardAuth = { signedIn: true, hasPermission: (p) => p === "agents.manage" };
const plain: GuardAuth = { signedIn: true, hasPermission: () => false };
const anon: GuardAuth = { signedIn: false, hasPermission: () => false };
const agentsPage = { name: "agents", fullPath: "/agents", permission: "agents.manage" };

describe("resolveGuard", () => {
  it("sends a guest to login with a redirect back", () => {
    expect(resolveGuard(agentsPage, anon)).toEqual({ name: "login", query: { redirect: "/agents" } });
  });
  it("lets a guest open the login page", () => {
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, anon)).toBe(true);
  });
  it("lets an agents.manage account open Agents", () => {
    expect(resolveGuard(agentsPage, admin)).toBe(true);
  });
  it("sends an account without the permission to no-access", () => {
    expect(resolveGuard(agentsPage, plain)).toEqual({ path: "/no-access" });
  });
  it("shows no-access to an account without the permission", () => {
    expect(resolveGuard({ name: "no-access", fullPath: "/no-access" }, plain)).toBe(true);
  });
  it("moves an admin off login and no-access to the first page", () => {
    expect(resolveGuard({ name: "login", fullPath: "/login", guestOnly: true }, admin)).toEqual({ path: "/agents" });
    expect(resolveGuard({ name: "no-access", fullPath: "/no-access" }, admin)).toEqual({ path: "/agents" });
  });
});
