import type { Account } from "../api/auth/AuthClient";

/** A signed-in member who may chat, run tools, attach files and share. */
export function makeAccount(overrides: Partial<Account> = {}): Account {
  return {
    id: 1,
    username: "root",
    email: "root@example.com",
    email_verified: true,
    roles: [],
    permissions: ["chat.use", "tools.execute", "files.upload", "files.download", "chat.share", "extensions.personal.manage"],
    ...overrides,
  };
}
