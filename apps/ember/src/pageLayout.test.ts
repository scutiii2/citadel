/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const features = join(dirname(fileURLToPath(import.meta.url)), "features");
const views = readdirSync(features, { recursive: true })
  .filter((name): name is string => typeof name === "string" && name.endsWith("View.vue"));
const EXEMPT = new Set([
  "ChatView.vue", "LoginView.vue", "RegisterView.vue", "VerifyEmailView.vue",
  "NoAccessView.vue", "SharedChatView.vue",
]);

describe("page layouts", () => {
  it("discovers feature views", () => {
    expect(views.length).toBeGreaterThan(EXEMPT.size);
  });

  for (const file of views.filter((name) => !EXEMPT.has(basename(name)))) {
    it(`${file} uses PageLayout for its wrapper and title`, () => {
      const source = readFileSync(join(features, file), "utf8");
      expect(source).toMatch(/<PageLayout(?:\s|>)/);
      const classes = [...source.matchAll(/(?<![:\w-])class\s*=\s*["']([^"']*)["']/g)]
        .flatMap((match) => match[1]!.split(/\s+/));
      expect(classes).not.toContain("page-column");
      expect(classes).not.toContain("page-title");
    });
  }
});
