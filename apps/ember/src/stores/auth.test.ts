import { createPinia } from "pinia";
import { expect, it } from "vitest";
import { useAuthStore } from "./auth";

it("requires verification for every signed-in account with an unverified email", () => {
  const auth = useAuthStore(createPinia());
  expect(auth.needsVerification).toBe(false);

  auth.account = {
    id: 1, username: "ada", email: "ada@example.com", email_verified: false,
    roles: ["Member"], permissions: ["chat.use"],
  };
  expect(auth.needsVerification).toBe(true);
  expect(auth.hasPermission("chat.use")).toBe(false);

  auth.account.email_verified = true;
  expect(auth.needsVerification).toBe(false);
  expect(auth.hasPermission("chat.use")).toBe(true);
});
