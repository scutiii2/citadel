/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { parse } from "vue/compiler-sfc";
import { describe, expect, it } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));
const featureRoot = join(root, "features");
const config = ts.readConfigFile(join(root, "../tsconfig.app.json"), ts.sys.readFile);
const options = ts.parseJsonConfigFileContent(config.config, ts.sys, resolve(root, "..")).options;

/** Parse dependencies rather than matching text: comments and strings aren't imports. */
function featureImports(file: string, source: string): string[] {
  const requests: string[] = [];
  let scripts = [source];
  if (file.endsWith(".vue")) {
    const { descriptor } = parse(source, { filename: file });
    scripts = [descriptor.script?.content, descriptor.scriptSetup?.content]
      .filter((content): content is string => content !== undefined);
    for (const block of [descriptor.script, descriptor.template, ...descriptor.styles]) {
      if (block?.src) requests.push(block.src);
    }
  }
  for (const script of scripts) {
    const ast = ts.createSourceFile(file, script, ts.ScriptTarget.Latest, true,
      file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
    const visit = (node: ts.Node): void => {
      if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
          node.moduleSpecifier && ts.isStringLiteralLike(node.moduleSpecifier)) {
        requests.push(node.moduleSpecifier.text);
      } else if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument) &&
                 ts.isStringLiteralLike(node.argument.literal)) {
        requests.push(node.argument.literal.text);
      } else if (ts.isCallExpression(node) &&
                 (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
                  (ts.isIdentifier(node.expression) && node.expression.text === "require"))) {
        const argument = node.arguments[0];
        if (argument && ts.isStringLiteralLike(argument)) requests.push(argument.text);
      } else if (ts.isExternalModuleReference(node) && node.expression && ts.isStringLiteralLike(node.expression)) {
        requests.push(node.expression.text);
      }
      ts.forEachChild(node, visit);
    };
    visit(ast);
  }
  return [...new Set(requests)].filter((request) => {
    const specifier = request.split("?")[0]!;
    const target = specifier.startsWith(".")
      ? resolve(dirname(file), specifier)
      : ts.resolveModuleName(specifier, file, options, ts.sys).resolvedModule?.resolvedFileName;
    if (!target) return false;
    const path = relative(featureRoot, target);
    return path === "" || (!isAbsolute(path) && path !== ".." && !path.startsWith("../") && !path.startsWith("..\\"));
  });
}

describe("shared module ownership", () => {
  it.each([
    'import { value } from "../features/chat/stores/chat";',
    'import type { Value } from "../features/chat/stores/chat";',
    'export { value } from "../features/chat/stores/chat";',
    'export type { Value } from "../features/chat/stores/chat";',
    'const value = import("../features/chat/stores/chat");',
    'type Value = typeof import("../features/chat/stores/chat");',
    'const value = require("../features/chat/stores/chat");',
  ])("detects feature dependencies in %s", (source) => {
    expect(featureImports(join(root, "utils/example.ts"), source)).toEqual(["../features/chat/stores/chat"]);
  });

  it("ignores comments and ordinary strings that look like imports", () => {
    expect(featureImports(join(root, "utils/example.ts"), `
      // import { value } from "../features/chat/stores/chat";
      const example = 'import("../features/chat/stores/chat")';
      import { apiRequest } from "../api/http";
    `)).toEqual([]);
  });

  it("checks Vue scripts and external style dependencies", () => {
    expect(featureImports(join(root, "components/Example.vue"), `
      <script setup lang="ts">import type { Value } from "../features/chat/stores/chat";</script>
      <template><div /></template>
      <style src="../features/chat/example.css"></style>
    `)).toEqual(["../features/chat/example.css", "../features/chat/stores/chat"]);
  });

  it("keeps shared code independent of features; layout and router compose them", () => {
    const files = ["api", "stores", "composables", "utils", "components"].flatMap((folder) =>
      readdirSync(join(root, folder), { recursive: true })
        .filter((name): name is string => typeof name === "string" && /\.(ts|tsx|vue)$/.test(name))
        .map((name) => join(root, folder, name)),
    ).filter((file) => !file.endsWith(".test.ts") &&
      !relative(root, file).replaceAll("\\", "/").startsWith("components/layout/"));
    expect(files.length).toBeGreaterThan(0);
    const violations = files.flatMap((file) => featureImports(file, readFileSync(file, "utf8"))
      .map((request) => `${relative(root, file).replaceAll("\\", "/")} imports ${request}`));
    expect(violations.sort()).toEqual([]);
  });
});
