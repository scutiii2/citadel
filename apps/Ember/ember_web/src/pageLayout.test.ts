/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const views = join(dirname(fileURLToPath(import.meta.url)), "views");
const EXEMPT = new Set([
  "ChatView.vue", "LoginView.vue", "RegisterView.vue", "VerifyEmailView.vue",
  "NoAccessView.vue", "SharedChatView.vue", "ConfigIssuesView.vue",
]);

describe("page layouts", () => {
  for (const file of readdirSync(views).filter((name) => name.endsWith(".vue") && !EXEMPT.has(name))) {
    it(`${file} uses PageLayout for its wrapper and title`, () => {
      const source = readFileSync(join(views, file), "utf8");
      expect(source).toMatch(/<PageLayout(?:\s|>)/);
      const classes = [...source.matchAll(/(?<![:\w-])class\s*=\s*["']([^"']*)["']/g)]
        .flatMap((match) => match[1]!.split(/\s+/));
      expect(classes).not.toContain("page-column");
      expect(classes).not.toContain("page-title");
    });
  }
});
